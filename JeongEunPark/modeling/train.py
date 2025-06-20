import torch
import torch.nn as nn
from torch import optim
from tqdm import tqdm
import os
import matplotlib.pyplot as plt
from early_stopping import EarlyStopping
from torch.optim.lr_scheduler import ReduceLROnPlateau
import datetime

def get_timestamped_dir(base_dir="state_dict"):
    timestamp = datetime.datetime.now().strftime("run_%Y%m%d_%H%M%S")
    full_path = os.path.join(base_dir, timestamp)
    os.makedirs(full_path, exist_ok=True)
    return full_path

def train_model(encoder, decoder, train_dataloader, val_dataloader, optimizer, device, num_epochs=1, patience=10, base_save_dir="state_dict"):
    save_dir = get_timestamped_dir(base_save_dir)

    scheduler = ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=15, verbose=True)
    early_stopper = EarlyStopping(patience=10, path=save_dir)

    # 학습 및 검증 손실을 저장할 리스트
    train_losses, val_losses = [], []

    for epoch in range(num_epochs):
        encoder.train()
        decoder.train()
        total_loss = 0

        loop = tqdm(train_dataloader, desc=f"[Epoch {epoch+1}]", mininterval=1.0)
        
        for images, input_ids, attention_mask, _  in loop:
            images = images.to(device)                 # [B, 3, 224, 224]
            input_ids = input_ids.to(device)           # [B, T]
            attention_mask = attention_mask.to(device) # [B, T]

            optimizer.zero_grad()

            features = encoder(images)

            outputs = decoder(
                features=features,
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=input_ids  # Hugging Face가 자동으로 CrossEntropyLoss 계산
            )
            loss = outputs.loss

            loss.backward()

            torch.nn.utils.clip_grad_norm_(
                list(encoder.parameters()) + list(decoder.parameters()), max_norm=1.0
            )

            optimizer.step()

            total_loss += loss.item()
            loop.set_postfix(loss=loss.item())

        avg_loss = total_loss / len(train_dataloader)
        val_loss = evaluate_model(encoder, decoder, val_dataloader, device)

        train_losses.append(avg_loss)
        val_losses.append(val_loss)

        print(f"[Epoch {epoch+1}] Train Loss: {avg_loss:.4f} | Val Loss: {val_loss:.4f}")
        
        scheduler.step(val_loss)

        # Save last (overwrite every epoch)
        torch.save(encoder.state_dict(), os.path.join(save_dir, "encoder_last.pt"))
        torch.save(decoder.state_dict(), os.path.join(save_dir, "decoder_last.pt"))
        
        # Save best if applicable
        early_stopper(avg_loss, encoder, decoder)
        if early_stopper.early_stop:
            print(f"[Epoch {epoch+1}] Early stopping triggered")
            break
        # if avg_loss <= 0.1:
        #     early_stopper(val_loss, encoder, decoder)
        #     if early_stopper.early_stop:
        #         print(f"[Epoch {epoch+1}] Early stopping triggered")
        #         break
        # else:
        #     print(f"[Epoch {epoch+1}] 아직 train loss > 0.1 → early stopping 미적용")
        
    # plot 저장
    plt.plot(train_losses, label='Train Loss')
    plt.plot(val_losses, label='Validation Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.title('Training and Validation Loss')
    plt.legend()
    plt.savefig('loss_plot_ep80_p15.png') 

def evaluate_model(encoder, decoder, val_dataloader, device):
    encoder.eval()
    decoder.eval()
    total_loss = 0

    with torch.no_grad():
        for images, input_ids, attention_mask, _ in val_dataloader:
            images = images.to(device)
            input_ids = input_ids.to(device)
            attention_mask = attention_mask.to(device)

            features = encoder(images)
            outputs = decoder(
                features=features,
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=input_ids
            )
            loss = outputs.loss
            total_loss += loss.item()

    val_loss = total_loss / len(val_dataloader)
    return val_loss