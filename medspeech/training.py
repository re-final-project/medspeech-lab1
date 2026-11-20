from pathlib import Path
import json
import random
import numpy as np
import soundfile as sf
from .data import dump


def train(root,rows,config,revisions,out):
    import torch
    from transformers import WhisperProcessor,WhisperForConditionalGeneration
    from peft import LoraConfig,get_peft_model
    random.seed(config["seed"]); np.random.seed(config["seed"]); torch.manual_seed(config["seed"])
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(config["seed"])
    torch.use_deterministic_algorithms(True,warn_only=True)
    processor=WhisperProcessor.from_pretrained(config["stt"],revision=revisions["stt"],language="Korean",task="transcribe")
    model=WhisperForConditionalGeneration.from_pretrained(config["stt"],revision=revisions["stt"])
    model=get_peft_model(model,LoraConfig(r=config["lora_rank"],lora_alpha=config["lora_alpha"],target_modules=["q_proj","v_proj"],lora_dropout=0.05,bias="none"))
    device="cuda" if torch.cuda.is_available() else "cpu"; model.to(device)
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=config["learning_rate"])
    def example(row):
        audio,sr=sf.read(Path(root)/row["audio_path"],dtype="float32")
        features=processor(audio,sampling_rate=sr,return_tensors="pt").input_features.to(device)
        labels=processor.tokenizer(row["transcript"],return_tensors="pt").input_ids.to(device)
        if labels[0,0]==model.config.decoder_start_token_id: labels=labels[:,1:]
        return features,labels
    train_rows=[r for r in rows if r["split"]=="train"]; dev=[r for r in rows if r["split"]=="validation"]
    logs=[]; best=float("inf"); out=Path(out); out.mkdir(parents=True,exist_ok=True)
    for epoch in range(config["epochs"]):
        model.train(); random.shuffle(train_rows); losses=[]
        for r in train_rows:
            features,labels=example(r); optimizer.zero_grad()
            loss=model(input_features=features,labels=labels).loss; loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); optimizer.step(); losses.append(loss.item())
        model.eval(); val=[]
        with torch.inference_mode():
            for r in dev:
                features,labels=example(r); val.append(model(input_features=features,labels=labels).loss.item())
        record=dict(epoch=epoch+1,train_loss=float(np.mean(losses)),validation_loss=float(np.mean(val)))
        logs.append(record); dump(out/"training_log.json",logs)
        print(f"LoRA epoch {epoch+1}: {record}",flush=True)
        if record["validation_loss"]<best:
            best=record["validation_loss"]; model.save_pretrained(out/"best"); processor.save_pretrained(out/"best")
        model.save_pretrained(out/f"epoch-{epoch+1}")
        torch.save(dict(optimizer=optimizer.state_dict(),epoch=epoch+1,torch_rng=torch.get_rng_state()),out/f"optimizer-{epoch+1}.pt")
    dump(out/"training_config.json",dict(config=config,revisions=revisions,device=device,batch_size_effective=1,
             train_ids=[r["sample_id"] for r in train_rows],validation_ids=[r["sample_id"] for r in dev]))
    return out/"best"
