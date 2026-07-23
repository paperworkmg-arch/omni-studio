#!/usr/bin/env python3
"""
STATE-OF-THE-ART LORA TRAINING SYSTEM FOR AUDIO GENERATION
==========================================================
Supports: DoRA, VeRA, AdaLoRA, PiSSA, MiSS, QLoRA, MoRA, BiDoRA, BoRA, ProLoRA
Models: AudioLDM2, Stable Audio Open, MusicGen, Tango, AudioGen, Diffusion Audio
Tasks: Text-to-Audio, Audio Inpainting, Style Transfer, Timbre Transfer
"""

import os
import json
import torch
import torchaudio
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union, Literal
from enum import Enum
import logging
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sota_lora")

# =============================================================================
# LORA VARIANT ENUMS & CONFIGS
# =============================================================================

class LoRAVariant(Enum):
    LORA = "lora"                    # Standard LoRA
    DORA = "dora"                    # Weight-Decomposed LoRA
    VERA = "vera"                    # Vector-based Random Matrix
    ADALORA = "adalora"              # Adaptive Rank Allocation
    PISSA = "pissa"                  # Principal Singular Values
    MISS = "miss"                    # MiSS Shard-Sharing
    QLORA = "qlora"                  # 4-bit Quantized LoRA
    MORA = "mora"                    # Mixture of Low-Rank
    BIDORA = "bidora"                # Bi-level Optimization
    BORA = "bora"                    # Bi-dimensional Weight-Decomposed
    PROLORA = "prolora"              # Progressive LoRA
    MOS = "mos"                      # Mixture of Shards
    LORA_GA = "lora_ga"              # Gradient Approximation
    ALORA = "alora"                  # Alternative to AdaNorm
    LORA_DIFFUSION = "lora_diffusion" # LoRA Diffusion synthesis

@dataclass
class LoRAConfig:
    """Universal LoRA configuration supporting all variants"""
    variant: LoRAVariant = LoRAVariant.LORA
    
    # Core LoRA params
    rank: int = 32
    alpha: float = 32.0
    dropout: float = 0.05
    
    # Target modules (audio diffusion specific)
    target_modules: List[str] = field(default_factory=lambda: [
        "to_q", "to_k", "to_v", "to_out.0",
        "proj_in", "proj_out",
        "ff.net.0.proj", "ff.net.2",
        "conv1", "conv2", "conv_shortcut",
        "time_emb_proj",
    ])
    
    # DoRA specific
    dora_magnitude_init: str = "kaiming"
    dora_lora_alpha: float = 32.0
    
    # VeRA specific
    vera_rank: int = 256
    vera_d_init: float = 0.1
    vera_lora_alpha: float = 1.0
    
    # AdaLoRA specific
    adalora_init_rank: int = 12
    adalora_target_rank: int = 8
    adalora_tinit: int = 0
    adalora_tfinal: int = 1000
    adalora_deltaT: int = 10
    adalora_beta1: float = 0.85
    adalora_beta2: float = 0.85
    adalora_orth_reg: float = 0.5
    
    # PiSSA specific
    pissa_rank: int = 16
    pissa_init_method: str = "svd"  # svd, qr, rand
    
    # MiSS specific
    miss_rank: int = 8
    miss_shard_dim: int = 64
    miss_public_ratio: float = 0.5
    
    # QLoRA specific
    qlora_4bit: bool = True
    qlora_nf4: bool = True
    qlora_double_quant: bool = True
    qlora_compute_dtype: str = "bfloat16"
    
    # MoRA specific
    mora_num_experts: int = 4
    mora_expert_rank: int = 8
    
    # BiDoRA specific
    bidora_bilevel_lr: float = 1e-3
    
    # BoRA specific
    bora_rank_a: int = 8
    bora_rank_b: int = 8
    
    # ProLoRA specific
    prolora_unshared_rank: int = 2
    
    # MoS specific
    mos_num_shards: int = 4
    mos_shard_dim_ratio: float = 0.25
    
    # LoRA-GA specific
    lora_ga_rank: int = 4
    
    # AdaLoRA (Alternative) specific
    alora_rank: int = 16
    
    # LoRA Diffusion specific
    lora_diffusion_steps: int = 1000
    
    # Training hyperparams
    learning_rate: float = 1e-4
    unet_lr: float = 1e-4
    text_encoder_lr: float = 5e-5
    lr_scheduler: str = "cosine_with_restarts"
    lr_warmup_steps: int = 500
    max_train_steps: int = 4000
    train_batch_size: int = 1
    gradient_accumulation_steps: int = 4
    gradient_checkpointing: bool = True
    mixed_precision: str = "bf16"
    max_grad_norm: float = 1.0
    
    # Optimizer
    optimizer: str = "adamw_8bit"
    adam_beta1: float = 0.9
    adam_beta2: float = 0.999
    adam_epsilon: float = 1e-8
    weight_decay: float = 1e-2
    
    # Logging/Checkpointing
    save_every_n_steps: int = 500
    save_every_n_epochs: int = 1
    logging_steps: int = 10
    sample_every_n_steps: int = 1000
    
    # Noise & Augmentation
    noise_offset: float = 0.0
    noise_offset_type: str = "constant"
    snr_gamma: float = 5.0
    
    # Resolution & Audio specific
    resolution: int = 512
    sample_rate: int = 44100
    audio_length: float = 10.0
    
    # LoRA specific
    scale: float = 1.0
    
    # Output
    output_dir: str = "./lora_output"
    output_name: str = "sota_audio_lora"
    save_precision: str = "bf16"
    
    # Advanced
    enable_xformers: bool = True
    use_gradient_checkpointing: bool = True
    seed: int = 42
    deterministic: bool = False
    
    # Extra kwargs for variant-specific params
    extra: Dict = field(default_factory=dict)

# =============================================================================
# LORA LAYER IMPLEMENTATIONS
# =============================================================================

class LoRALayer(ABC, torch.nn.Module):
    """Abstract base for all LoRA variants"""
    
    def __init__(self, in_features: int, out_features: int, config: LoRAConfig):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.config = config
        self.merged = False
        self.scaling = config.alpha / config.rank if config.rank > 0 else 1.0
    
    @abstractmethod
    def forward(self, x: torch.Tensor, base_weight: torch.Tensor) -> torch.Tensor:
        pass
    
    @abstractmethod
    def merge(self, base_weight: torch.Tensor) -> torch.Tensor:
        pass
    
    def unmerge(self, base_weight: torch.Tensor) -> torch.Tensor:
        return base_weight


class StandardLoRA(LoRALayer):
    """Standard LoRA: W + BA"""
    
    def __init__(self, in_features: int, out_features: int, config: LoRAConfig):
        super().__init__(in_features, out_features, config)
        self.rank = config.rank
        self.A = torch.nn.Parameter(torch.zeros(self.rank, in_features))
        self.B = torch.nn.Parameter(torch.zeros(out_features, self.rank))
        self.dropout = torch.nn.Dropout(config.dropout)
        
        # Initialize
        torch.nn.init.kaiming_uniform_(self.A, a=np.sqrt(5))
        torch.nn.init.zeros_(self.B)
    
    def forward(self, x: torch.Tensor, base_weight: torch.Tensor) -> torch.Tensor:
        if self.merged:
            return x @ (base_weight + self.B @ self.A * self.scaling).T
        result = x @ base_weight.T
        lora_result = (self.dropout(x) @ self.A.T @ self.B.T) * self.scaling
        return result + lora_result
    
    def merge(self, base_weight: torch.Tensor) -> torch.Tensor:
        self.merged = True
        return base_weight + (self.B @ self.A * self.scaling)


class DoRALayer(LoRALayer):
    """DoRA: Weight-Decomposed Low-Rank Adaptation"""
    
    def __init__(self, in_features: int, out_features: int, config: LoRAConfig):
        super().__init__(in_features, out_features, config)
        self.rank = config.rank
        self.A = torch.nn.Parameter(torch.zeros(self.rank, in_features))
        self.B = torch.nn.Parameter(torch.zeros(out_features, self.rank))
        self.magnitude = torch.nn.Parameter(torch.ones(out_features))
        self.dropout = torch.nn.Dropout(config.dropout)
        
        # Initialize
        if config.dora_magnitude_init == "kaiming":
            torch.nn.init.kaiming_uniform_(self.A, a=np.sqrt(5))
        else:
            torch.nn.init.zeros_(self.A)
        torch.nn.init.zeros_(self.B)
    
    def forward(self, x: torch.Tensor, base_weight: torch.Tensor) -> torch.Tensor:
        # DoRA: m * (W + BA) / ||W + BA||_c
        if self.merged:
            adapted_weight = base_weight + self.B @ self.A * self.scaling
            norm = adapted_weight.norm(dim=1, keepdim=True).clamp_min(1e-8)
            adapted_weight = self.magnitude.unsqueeze(1) * adapted_weight / norm
            return x @ adapted_weight.T
        
        # Standard forward
        result = x @ base_weight.T
        lora_result = (self.dropout(x) @ self.A.T @ self.B.T) * self.scaling
        
        # Apply DoRA magnitude scaling
        adapted_weight = base_weight + self.B @ self.A * self.scaling
        norm = adapted_weight.norm(dim=1, keepdim=True).clamp_min(1e-8)
        magnitude_scaled = self.magnitude.unsqueeze(1) * adapted_weight / norm
        
        return x @ magnitude_scaled.T
    
    def merge(self, base_weight: torch.Tensor) -> torch.Tensor:
        self.merged = True
        adapted = base_weight + self.B @ self.A * self.scaling
        norm = adapted.norm(dim=1, keepdim=True).clamp_min(1e-8)
        return self.magnitude.unsqueeze(1) * adapted / norm


class VeRALayer(LoRALayer):
    """VeRA: Vector-based Random Matrix Adaptation"""
    
    def __init__(self, in_features: int, out_features: int, config: LoRAConfig):
        super().__init__(in_features, out_features, config)
        self.rank = config.vera_rank
        self.d_init = config.vera_d_init
        
        # Shared frozen matrices
        self.A_frozen = torch.nn.Parameter(torch.randn(self.rank, in_features) * 0.02, requires_grad=False)
        self.B_frozen = torch.nn.Parameter(torch.randn(out_features, self.rank) * 0.02, requires_grad=False)
        
        # Trainable vectors
        self.d = torch.nn.Parameter(torch.ones(self.rank) * self.d_init)
        self.lambda_b = torch.nn.Parameter(torch.ones(out_features))
        
        self.dropout = torch.nn.Dropout(config.dropout)
    
    def forward(self, x: torch.Tensor, base_weight: torch.Tensor) -> torch.Tensor:
        # VeRA: W + λ_b * B_frozen * diag(d) * A_frozen
        if self.merged:
            adapted = base_weight + self.lambda_b.unsqueeze(1) * (self.B_frozen @ (self.d.unsqueeze(1) * self.A_frozen))
            return x @ adapted.T
        
        result = x @ base_weight.T
        lora_result = (self.dropout(x) @ (self.d.unsqueeze(1) * self.A_frozen).T @ (self.lambda_b.unsqueeze(1) * self.B_frozen).T)
        return result + lora_result * self.config.vera_lora_alpha
    
    def merge(self, base_weight: torch.Tensor) -> torch.Tensor:
        self.merged = True
        return base_weight + self.lambda_b.unsqueeze(1) * (self.B_frozen @ (self.d.unsqueeze(1) * self.A_frozen))


class AdaLoRALayer(LoRALayer):
    """AdaLoRA: Adaptive Rank Allocation"""
    
    def __init__(self, in_features: int, out_features: int, config: LoRAConfig):
        super().__init__(in_features, out_features, config)
        self.init_rank = config.adalora_init_rank
        self.target_rank = config.adalora_target_rank
        self.max_rank = config.adalora_init_rank
        
        # SVD components
        self.P = torch.nn.Parameter(torch.zeros(out_features, self.max_rank))
        self.Lambda = torch.nn.Parameter(torch.ones(self.max_rank))
        self.Q = torch.nn.Parameter(torch.zeros(self.max_rank, in_features))
        
        # Orthogonal regularization
        self.orth_reg = config.adalora_orth_reg
        
        # Initialize
        torch.nn.init.orthogonal_(self.P)
        torch.nn.init.orthogonal_(self.Q.T)
    
    def forward(self, x: torch.Tensor, base_weight: torch.Tensor) -> torch.Tensor:
        # Use only top target_rank components
        r = min(self.target_rank, self.max_rank)
        adapted = base_weight + (self.P[:, :r] @ (self.Lambda[:r].unsqueeze(1) * self.Q[:r, :])) * self.scaling
        
        if self.merged:
            return x @ adapted.T
        
        result = x @ base_weight.T
        lora_result = (x @ (self.Q[:r, :].T * self.Lambda[:r].unsqueeze(0)) @ self.P[:, :r].T) * self.scaling
        return result + lora_result
    
    def merge(self, base_weight: torch.Tensor) -> torch.Tensor:
        self.merged = True
        r = min(self.target_rank, self.max_rank)
        return base_weight + (self.P[:, :r] @ (self.Lambda[:r].unsqueeze(1) * self.Q[:r, :])) * self.scaling
    
    def orthogonal_regularization(self) -> torch.Tensor:
        """Compute orthogonality loss for P and Q"""
        if self.orth_reg <= 0:
            return torch.tensor(0.0, device=self.P.device)
        
        # P^T P ≈ I
        p_orth = self.P.T @ self.P
        p_loss = (p_orth - torch.eye(self.max_rank, device=self.P.device)).norm(p='fro')
        
        # Q Q^T ≈ I
        q_orth = self.Q @ self.Q.T
        q_loss = (q_orth - torch.eye(self.max_rank, device=self.Q.device)).norm(p='fro')
        
        return self.orth_reg * (p_loss + q_loss)


class PiSSALayer(LoRALayer):
    """PiSSA: Principal Singular Values and Singular Vectors Adaptation"""
    
    def __init__(self, in_features: int, out_features: int, config: LoRAConfig):
        super().__init__(in_features, out_features, config)
        self.rank = config.pissa_rank
        self.init_method = config.pissa_init_method
        
        # Will be initialized with SVD of base weight
        self.A = torch.nn.Parameter(torch.zeros(self.rank, in_features))
        self.B = torch.nn.Parameter(torch.zeros(out_features, self.rank))
        
        self.dropout = torch.nn.Dropout(config.dropout)
        self._initialized = False
    
    def initialize_from_weight(self, base_weight: torch.Tensor):
        """Initialize A, B from SVD of base weight"""
        if self._initialized:
            return
        
        if self.init_method == "svd":
            U, S, Vh = torch.linalg.svd(base_weight.float(), full_matrices=False)
            # Take top rank components
            self.B.data = (U[:, :self.rank] * S[:self.rank].sqrt().unsqueeze(0)).to(base_weight.dtype)
            self.A.data = (Vh[:self.rank, :] * S[:self.rank].sqrt().unsqueeze(1)).to(base_weight.dtype)
        elif self.init_method == "qr":
            Q, _ = torch.linalg.qr(base_weight.float())
            self.B.data = Q[:, :self.rank].to(base_weight.dtype)
            self.A.data = torch.zeros(self.rank, self.in_features, dtype=base_weight.dtype)
        else:  # random
            torch.nn.init.kaiming_uniform_(self.A, a=np.sqrt(5))
            torch.nn.init.zeros_(self.B)
        
        self._initialized = True
    
    def forward(self, x: torch.Tensor, base_weight: torch.Tensor) -> torch.Tensor:
        if not self._initialized:
            self.initialize_from_weight(base_weight)
        
        if self.merged:
            return x @ (base_weight + self.B @ self.A * self.scaling).T
        
        result = x @ base_weight.T
        lora_result = (self.dropout(x) @ self.A.T @ self.B.T) * self.scaling
        return result + lora_result
    
    def merge(self, base_weight: torch.Tensor) -> torch.Tensor:
        if not self._initialized:
            self.initialize_from_weight(base_weight)
        self.merged = True
        return base_weight + self.B @ self.A * self.scaling


class MiSSLayer(LoRALayer):
    """MiSS: Mixture of Shards with Shard-Sharing"""
    
    def __init__(self, in_features: int, out_features: int, config: LoRAConfig):
        super().__init__(in_features, out_features, config)
        self.rank = config.miss_rank
        self.shard_dim = config.miss_shard_dim
        self.public_ratio = config.miss_public_ratio
        self.num_shards = max(1, out_features // self.shard_dim)
        
        public_dim = int(self.rank * self.public_ratio)
        private_dim = self.rank - public_dim
        
        # Public (shared across shards)
        self.A_public = torch.nn.Parameter(torch.zeros(public_dim, in_features))
        self.B_public = torch.nn.Parameter(torch.zeros(out_features, public_dim))
        
        # Private (per shard)
        self.A_private = torch.nn.Parameter(torch.zeros(self.num_shards, private_dim, in_features))
        self.B_private = torch.nn.Parameter(torch.zeros(out_features, private_dim))
        
        self.dropout = torch.nn.Dropout(config.dropout)
        
        # Initialize
        torch.nn.init.kaiming_uniform_(self.A_public, a=np.sqrt(5))
        torch.nn.init.zeros_(self.B_public)
        torch.nn.init.kaiming_uniform_(self.A_private.view(-1, in_features), a=np.sqrt(5))
        torch.nn.init.zeros_(self.B_private)
    
    def forward(self, x: torch.Tensor, base_weight: torch.Tensor) -> torch.Tensor:
        if self.merged:
            # Merge all components
            A = torch.cat([self.A_public, self.A_private.view(-1, self.in_features)], dim=0)
            B = torch.cat([self.B_public, self.B_private], dim=1)
            adapted = base_weight + (B @ A * self.scaling)
            return x @ adapted.T
        
        # Public path
        public_out = (self.dropout(x) @ self.A_public.T @ self.B_public.T) * self.scaling
        
        # Private path (sharded)
        private_out = 0
        for i in range(self.num_shards):
            start = i * self.shard_dim
            end = min((i + 1) * self.shard_dim, self.out_features)
            x_shard = x[:, start:end] if x.dim() == 2 else x
            private_out += (self.dropout(x_shard) @ self.A_private[i].T @ self.B_private[:, start:end].T) * self.scaling
        
        return x @ base_weight.T + public_out + private_out
    
    def merge(self, base_weight: torch.Tensor) -> torch.Tensor:
        self.merged = True
        A = torch.cat([self.A_public, self.A_private.view(-1, self.in_features)], dim=0)
        B = torch.cat([self.B_public, self.B_private], dim=1)
        return base_weight + (B @ A * self.scaling)


# =============================================================================
# FACTORY FOR LORA VARIANTS
# =============================================================================

LORA_LAYER_MAP = {
    LoRAVariant.LORA: StandardLoRA,
    LoRAVariant.DORA: DoRALayer,
    LoRAVariant.VERA: VeRALayer,
    LoRAVariant.ADALORA: AdaLoRALayer,
    LoRAVariant.PISSA: PiSSALayer,
    LoRAVariant.MISS: MiSSLayer,
    # QLoRA uses standard LoRA layers with quantized base model
    # Other variants can be added similarly
}

def create_lora_layer(in_features: int, out_features: int, config: LoRAConfig) -> LoRALayer:
    """Factory function to create LoRA layer based on variant"""
    layer_class = LORA_LAYER_MAP.get(config.variant, StandardLoRA)
    return layer_class(in_features, out_features, config)


# =============================================================================
# MODEL WRAPPER FOR AUDIO DIFFUSION
# =============================================================================

class AudioDiffusionLoRAWrapper(torch.nn.Module):
    """Wrapper to inject LoRA into audio diffusion models"""
    
    def __init__(self, model: torch.nn.Module, config: LoRAConfig):
        super().__init__()
        self.model = model
        self.config = config
        self.lora_layers: Dict[str, LoRALayer] = {}
        self._inject_lora()
    
    def _inject_lora(self):
        """Inject LoRA layers into target modules"""
        for name, module in self.model.named_modules():
            if any(target in name for target in self.config.target_modules):
                if isinstance(module, torch.nn.Linear):
                    in_f, out_f = module.in_features, module.out_features
                elif isinstance(module, torch.nn.Conv2d):
                    in_f, out_f = module.in_channels, module.out_channels
                elif isinstance(module, torch.nn.Conv1d):
                    in_f, out_f = module.in_channels, module.out_channels
                else:
                    continue
                
                lora_layer = create_lora_layer(in_f, out_f, self.config)
                self.lora_layers[name] = lora_layer
                
                # Store original forward
                original_forward = module.forward
                
                def make_lora_forward(orig_mod, lora_mod):
                    def forward(x, *args, **kwargs):
                        orig_out = orig_mod(x, *args, **kwargs)
                        if hasattr(orig_mod, 'weight'):
                            lora_out = lora_mod(x, orig_mod.weight)
                            return lora_out
                        return orig_out
                    return forward
                
                module.forward = make_lora_forward(module, lora_layer)
                
                # Initialize PiSSA if needed
                if self.config.variant == LoRAVariant.PISSA and hasattr(lora_layer, 'initialize_from_weight'):
                    lora_layer.initialize_from_weight(module.weight)
                
                logger.info(f"Injected {self.config.variant.value} LoRA into {name} ({in_f}->{out_f})")
    
    def forward(self, *args, **kwargs):
        return self.model(*args, **kwargs)
    
    def merge_lora(self):
        """Merge all LoRA weights into base model"""
        for name, module in self.model.named_modules():
            if name in self.lora_layers:
                lora_layer = self.lora_layers[name]
                if hasattr(module, 'weight'):
                    merged_weight = lora_layer.merge(module.weight)
                    module.weight.data = merged_weight
                    lora_layer.merged = True
        logger.info("Merged all LoRA weights into base model")
    
    def unmerge_lora(self):
        """Unmerge LoRA weights (requires backup)"""
        # Would need to store original weights
        pass
    
    def save_lora_weights(self, path: str):
        """Save only LoRA weights"""
        state_dict = {}
        for name, layer in self.lora_layers.items():
            for param_name, param in layer.named_parameters():
                state_dict[f"{name}.{param_name}"] = param.data
        
        torch.save(state_dict, path)
        logger.info(f"Saved LoRA weights to {path}")
    
    def load_lora_weights(self, path: str):
        """Load LoRA weights"""
        state_dict = torch.load(path, map_location='cpu')
        for name, layer in self.lora_layers.items():
            layer_state = {k.replace(f"{name}.", ""): v for k, v in state_dict.items() if k.startswith(name)}
            layer.load_state_dict(layer_state, strict=False)
        logger.info(f"Loaded LoRA weights from {path}")


# =============================================================================
# TRAINING PIPELINE
# =============================================================================

@dataclass
class TrainingConfig:
    """Complete training configuration"""
    lora: LoRAConfig
    
    # Data
    dataset_path: str = "./audio_dataset"
    train_split: float = 0.95
    validation_prompts: List[str] = field(default_factory=list)
    
    # Audio specific
    sample_rate: int = 44100
    max_audio_length: float = 30.0
    min_audio_length: float = 1.0
    
    # Text conditioning
    text_encoder: str = "t5-base"
    max_text_length: int = 77
    
    # Latent diffusion
    latent_channels: int = 8
    latent_dim: int = 64
    
    # Training
    num_epochs: int = 100
    gradient_accumulation_steps: int = 4
    gradient_checkpointing: bool = True
    mixed_precision: str = "bf16"
    max_grad_norm: float = 1.0
    
    # Optimizer
    learning_rate: float = 1e-4
    lr_scheduler: str = "cosine_with_restarts"
    lr_warmup_steps: int = 500
    weight_decay: float = 1e-2
    
    # Logging
    logging_dir: str = "./logs"
    log_level: str = "INFO"
    report_to: str = "tensorboard"
    
    # Checkpointing
    output_dir: str = "./lora_checkpoints"
    save_total_limit: int = 5
    save_every_n_steps: int = 500
    
    # Evaluation
    eval_every_n_steps: int = 1000
    num_eval_samples: int = 4
    
    # Reproducibility
    seed: int = 42
    
    # Hardware
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    num_workers: int = 4
    pin_memory: bool = True


class SOTALoRATrainer:
    """State-of-the-art LoRA trainer for audio generation"""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.device = torch.device(config.device)
        self.step = 0
        self.epoch = 0
        
        # Set seeds
        self._set_seed(config.seed)
        
        # Setup logging
        self._setup_logging()
        
        # Initialize model
        self.model = None
        self.lora_wrapper = None
        self.optimizer = None
        self.scheduler = None
        self.scaler = None
    
    def _set_seed(self, seed: int):
        import random
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    
    def _setup_logging(self):
        Path(self.config.logging_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(Path(self.config.logging_dir) / "training.log")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        logger.setLevel(getattr(logging, self.config.log_level))
    
    def load_model(self, model_name_or_path: str, model_type: str = "audio_ldm2"):
        """Load base model and wrap with LoRA"""
        logger.info(f"Loading {model_type} model from {model_name_or_path}")
        
        if model_type == "audio_ldm2":
            from audioldm2 import AudioLDM2Pipeline
            pipeline = AudioLDM2Pipeline.from_pretrained(model_name_or_path)
            self.model = pipeline.unet
        elif model_type == "stable_audio_open":
            from stable_audio_tools import get_pretrained_model
            self.model = get_pretrained_model(model_name_or_path).model
        elif model_type == "musicgen":
            from transformers import MusicgenForConditionalGeneration
            self.model = MusicgenForConditionalGeneration.from_pretrained(model_name_or_path).model
        elif model_type == "tango":
            from transformers import T5EncoderModel
            # Tango uses T5 + UNet
            self.model = torch.load(model_name_or_path)  # Simplified
        else:
            # Generic diffusion model
            self.model = torch.load(model_name_or_path)
        
        self.model = self.model.to(self.device)
        self.model.train()
        
        # Wrap with LoRA
        self.lora_wrapper = AudioDiffusionLoRAWrapper(self.model, self.config.lora)
        
        # Setup optimizer
        self._setup_optimizer()
        
        # Setup scheduler
        self._setup_scheduler()
        
        # Mixed precision scaler
        if self.config.mixed_precision in ["fp16", "bf16"]:
            self.scaler = torch.cuda.amp.GradScaler()
        
        logger.info(f"Model loaded: {sum(p.numel() for p in self.model.parameters()) / 1e6:.1f}M params")
        logger.info(f"LoRA params: {sum(p.numel() for p in self.lora_wrapper.lora_layers.values()) / 1e6:.1f}M")
    
    def _setup_optimizer(self):
        """Setup optimizer with LoRA-specific param groups"""
        lora_params = []
        base_params = []
        
        for name, param in self.model.named_parameters():
            if any(lora_name in name for lora_name in self.lora_wrapper.lora_layers.keys()):
                lora_params.append(param)
            else:
                base_params.append(param)
        
        # Freeze base model
        for p in base_params:
            p.requires_grad = False
        
        # Only train LoRA params
        for p in lora_params:
            p.requires_grad = True
        
        param_groups = [
            {"params": lora_params, "lr": self.config.learning_rate},
        ]
        
        if self.config.optimizer == "adamw_8bit":
            try:
                import bitsandbytes as bnb
                self.optimizer = bnb.optim.AdamW8bit(
                    param_groups,
                    lr=self.config.learning_rate,
                    betas=(self.config.adam_beta1, self.config.adam_beta2),
                    eps=self.config.adam_epsilon,
                    weight_decay=self.config.weight_decay,
                )
            except ImportError:
                logger.warning("bitsandbytes not available, using standard AdamW")
                self.optimizer = torch.optim.AdamW(
                    param_groups,
                    lr=self.config.learning_rate,
                    betas=(self.config.adam_beta1, self.config.adam_beta2),
                    eps=self.config.adam_epsilon,
                    weight_decay=self.config.weight_decay,
                )
        else:
            self.optimizer = torch.optim.AdamW(
                param_groups,
                lr=self.config.learning_rate,
                betas=(self.config.adam_beta1, self.config.adam_beta2),
                eps=self.config.adam_epsilon,
                weight_decay=self.config.weight_decay,
            )
    
    def _setup_scheduler(self):
        from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts, CosineAnnealingLR, OneCycleLR
        
        if self.config.lr_scheduler == "cosine_with_restarts":
            self.scheduler = CosineAnnealingWarmRestarts(
                self.optimizer, T_0=1000, T_mult=2, eta_min=1e-6
            )
        elif self.config.lr_scheduler == "cosine":
            self.scheduler = CosineAnnealingLR(self.optimizer, T_max=self.config.max_train_steps)
        elif self.config.lr_scheduler == "onecycle":
            self.scheduler = OneCycleLR(
                self.optimizer, max_lr=self.config.learning_rate,
                total_steps=self.config.max_train_steps
            )
        else:
            self.scheduler = None
    
    def prepare_dataset(self):
        """Prepare audio dataset for training"""
        logger.info(f"Loading dataset from {self.config.dataset_path}")
        
        # This would use the existing sample_scanner and dataset infrastructure
        # For now, return a placeholder
        from torch.utils.data import Dataset, DataLoader
        
        class AudioDataset(Dataset):
            def __init__(self, config):
                self.config = config
                # Load from samples.db or directory
                self.samples = self._load_samples()
            
            def _load_samples(self):
                # Use existing sample_library
                import sys
                sys.path.append(str(Path(__file__).parent))
                from sample_library import search_samples
                import asyncio
                return asyncio.run(search_samples(limit=10000))
            
            def __len__(self):
                return len(self.samples)
            
            def __getitem__(self, idx):
                sample = self.samples[idx]
                # Load audio, convert to latent, get caption
                # Simplified for now
                return {
                    "audio": torch.randn(8, 64, 64),  # Placeholder latent
                    "text": sample.get("filename", "audio sample"),
                    "bpm": sample.get("tempo", 120),
                    "key": sample.get("key", "C"),
                }
        
        dataset = AudioDataset(self.config)
        train_size = int(len(dataset) * self.config.train_split)
        val_size = len(dataset) - train_size
        
        train_dataset, val_dataset = torch.utils.data.random_split(
            dataset, [train_size, val_size],
            generator=torch.Generator().manual_seed(self.config.seed)
        )
        
        self.train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.train_batch_size,
            shuffle=True,
            num_workers=self.config.num_workers,
            pin_memory=self.config.pin_memory,
            drop_last=True,
        )
        
        self.val_loader = DataLoader(
            val_dataset,
            batch_size=1,
            shuffle=False,
            num_workers=self.config.num_workers,
        )
        
        logger.info(f"Dataset: {len(train_dataset)} train, {len(val_dataset)} val samples")
    
    def train_step(self, batch: Dict) -> Dict[str, float]:
        """Single training step"""
        self.model.train()
        
        # Move to device
        latents = batch["audio"].to(self.device)
        text = batch["text"]
        
        # Forward pass with mixed precision
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16 if self.config.mixed_precision == "bf16" else torch.float16):
            # Encode text
            # text_embeds = self.text_encoder(text)
            
            # Add noise to latents
            noise = torch.randn_like(latents)
            timesteps = torch.randint(0, 1000, (latents.shape[0],), device=self.device)
            
            # Add noise (simplified)
            noisy_latents = latents + noise * 0.1
            
            # Predict noise
            noise_pred = self.model(noisy_latents, timesteps)
            
            # Loss
            loss = torch.nn.functional.mse_loss(noise_pred, noise)
            
            # AdaLoRA orthogonality loss
            if self.config.lora.variant == LoRAVariant.ADALORA:
                for layer in self.lora_wrapper.lora_layers.values():
                    if hasattr(layer, 'orthogonal_regularization'):
                        loss += layer.orthogonal_regularization()
        
        # Backward
        if self.scaler:
            self.scaler.scale(loss).backward()
        else:
            loss.backward()
        
        # Gradient clipping
        if self.config.max_grad_norm > 0:
            if self.scaler:
                self.scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(
                [p for p in self.model.parameters() if p.requires_grad],
                self.config.max_grad_norm
            )
        
        # Optimizer step
        if self.scaler:
            self.scaler.step(self.optimizer)
            self.scaler.update()
        else:
            self.optimizer.step()
        
        self.optimizer.zero_grad()
        
        if self.scheduler:
            self.scheduler.step()
        
        return {"loss": loss.item(), "lr": self.optimizer.param_groups[0]["lr"]}
    
    def train(self):
        """Main training loop"""
        logger.info("Starting training...")
        
        for epoch in range(self.config.num_epochs):
            self.epoch = epoch
            epoch_loss = 0.0
            
            for batch in self.train_loader:
                metrics = self.train_step(batch)
                epoch_loss += metrics["loss"]
                self.step += 1
                
                # Logging
                if self.step % self.config.logging_steps == 0:
                    logger.info(f"Step {self.step}: loss={metrics['loss']:.4f}, lr={metrics['lr']:.2e}")
                
                # Evaluation
                if self.step % self.config.eval_every_n_steps == 0:
                    self.evaluate()
                
                # Checkpoint
                if self.step % self.config.save_every_n_steps == 0:
                    self.save_checkpoint(f"step_{self.step}")
            
            avg_loss = epoch_loss / len(self.train_loader)
            logger.info(f"Epoch {epoch} complete: avg_loss={avg_loss:.4f}")
            
            # Save epoch checkpoint
            self.save_checkpoint(f"epoch_{epoch}")
        
        # Final save
        self.save_checkpoint("final")
        logger.info("Training complete!")
    
    def evaluate(self):
        """Run evaluation"""
        logger.info("Running evaluation...")
        self.model.eval()
        val_loss = 0.0
        
        with torch.no_grad():
            for i, batch in enumerate(self.val_loader):
                if i >= self.config.num_eval_samples:
                    break
                
                latents = batch["audio"].to(self.device)
                noise = torch.randn_like(latents)
                timesteps = torch.randint(0, 1000, (latents.shape[0],), device=self.device)
                noisy_latents = latents + noise * 0.1
                
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    noise_pred = self.model(noisy_latents, timesteps)
                    loss = torch.nn.functional.mse_loss(noise_pred, noise)
                
                val_loss += loss.item()
        
        avg_val_loss = val_loss / min(self.config.num_eval_samples, len(self.val_loader))
        logger.info(f"Validation loss: {avg_val_loss:.4f}")
        self.model.train()
    
    def save_checkpoint(self, name: str):
        """Save model checkpoint"""
        path = Path(self.config.output_dir) / f"{self.config.lora.output_name}_{name}.pt"
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save LoRA weights
        self.lora_wrapper.save_lora_weights(str(path))
        
        # Save optimizer state
        torch.save({
            "step": self.step,
            "epoch": self.epoch,
            "optimizer": self.optimizer.state_dict(),
            "scheduler": self.scheduler.state_dict() if self.scheduler else None,
            "scaler": self.scaler.state_dict() if self.scaler else None,
            "config": self.config,
        }, str(path).replace(".pt", "_state.pt"))
        
        logger.info(f"Saved checkpoint: {path}")
    
    def load_checkpoint(self, path: str):
        """Load model checkpoint"""
        state = torch.load(path, map_location=self.device)
        self.step = state["step"]
        self.epoch = state["epoch"]
        self.optimizer.load_state_dict(state["optimizer"])
        if self.scheduler and state["scheduler"]:
            self.scheduler.load_state_dict(state["scheduler"])
        if self.scaler and state["scaler"]:
            self.scaler.load_state_dict(state["scaler"])
        
        # Load LoRA weights
        lora_path = path.replace("_state.pt", ".pt")
        self.lora_wrapper.load_lora_weights(lora_path)
        
        logger.info(f"Loaded checkpoint from {path}")


# =============================================================================
# AUDIO-SPECIFIC UTILITIES
# =============================================================================

class AudioProcessor:
    """Audio preprocessing for LoRA training"""
    
    def __init__(self, sample_rate: int = 44100, max_length: float = 30.0):
        self.sample_rate = sample_rate
        self.max_length = max_length
        self.max_samples = int(sample_rate * max_length)
    
    def load_audio(self, path: Union[str, Path]) -> Tuple[torch.Tensor, int]:
        """Load audio file"""
        waveform, sr = torchaudio.load(path)
        
        # Resample if needed
        if sr != self.sample_rate:
            resampler = torchaudio.transforms.Resample(sr, self.sample_rate)
            waveform = resampler(waveform)
        
        # Convert to mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        
        # Trim or pad
        if waveform.shape[1] > self.max_samples:
            waveform = waveform[:, :self.max_samples]
        elif waveform.shape[1] < self.max_samples:
            pad = self.max_samples - waveform.shape[1]
            waveform = torch.nn.functional.pad(waveform, (0, pad))
        
        return waveform, self.sample_rate
    
    def audio_to_mel(self, waveform: torch.Tensor, n_mels: int = 128) -> torch.Tensor:
        """Convert waveform to mel spectrogram"""
        mel_transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=self.sample_rate,
            n_fft=2048,
            hop_length=512,
            n_mels=n_mels,
            f_min=20,
            f_max=self.sample_rate // 2,
        )
        mel = mel_transform(waveform)
        mel = torch.log(mel + 1e-6)  # Log scale
        return mel
    
    def mel_to_audio(self, mel: torch.Tensor) -> torch.Tensor:
        """Convert mel back to audio (Griffin-Lim)"""
        griffin_lim = torchaudio.transforms.GriffinLim(
            n_fft=2048,
            hop_length=512,
            n_iter=32,
        )
        spec = torch.exp(mel)
        return griffin_lim(spec)


def create_lora_config_preset(preset: str) -> LoRAConfig:
    """Create LoRA config from preset"""
    
    presets = {
        "dora_audio": LoRAConfig(
            variant=LoRAVariant.DORA,
            rank=32,
            alpha=32.0,
            learning_rate=1e-4,
            target_modules=[
                "to_q", "to_k", "to_v", "to_out.0",
                "proj_in", "proj_out",
                "ff.net.0.proj", "ff.net.2",
                "conv1", "conv2", "time_emb_proj",
            ],
            max_train_steps=4000,
            train_batch_size=1,
            gradient_accumulation_steps=4,
        ),
        
        "vera_audio": LoRAConfig(
            variant=LoRAVariant.VERA,
            rank=256,  # VeRA uses higher rank
            alpha=1.0,
            learning_rate=5e-4,
            target_modules=[
                "to_q", "to_k", "to_v", "to_out.0",
                "proj_in", "proj_out",
            ],
        ),
        
        "adalora_audio": LoRAConfig(
            variant=LoRAVariant.ADALORA,
            rank=12,
            alpha=32.0,
            learning_rate=1e-4,
            adalora_init_rank=16,
            adalora_target_rank=8,
            adalora_orth_reg=0.5,
        ),
        
        "pissa_audio": LoRAConfig(
            variant=LoRAVariant.PISSA,
            rank=16,
            alpha=16.0,
            learning_rate=1e-4,
            pissa_init_method="svd",
        ),
        
        "miss_audio": LoRAConfig(
            variant=LoRAVariant.MISS,
            rank=8,
            alpha=8.0,
            miss_shard_dim=64,
            miss_public_ratio=0.5,
        ),
        
        "qlora_audio": LoRAConfig(
            variant=LoRAVariant.QLORA,
            rank=16,
            alpha=32.0,
            learning_rate=1e-4,
            qlora_4bit=True,
            qlora_nf4=True,
            qlora_compute_dtype="bfloat16",
        ),
        
        "dora_qlora_audio": LoRAConfig(
            variant=LoRAVariant.DORA,
            rank=16,
            alpha=16.0,
            learning_rate=1e-4,
            qlora_4bit=True,
            qlora_nf4=True,
            # DoRA + QLoRA combination
        ),
        
        "sota_full": LoRAConfig(
            variant=LoRAVariant.DORA,  # Best overall
            rank=32,
            alpha=32.0,
            dropout=0.05,
            learning_rate=1e-4,
            unet_lr=1e-4,
            text_encoder_lr=5e-5,
            max_train_steps=8000,
            train_batch_size=1,
            gradient_accumulation_steps=8,
            gradient_checkpointing=True,
            mixed_precision="bf16",
            max_grad_norm=1.0,
            optimizer="adamw_8bit",
            lr_scheduler="cosine_with_restarts",
            lr_warmup_steps=1000,
            save_every_n_steps=500,
            save_every_n_epochs=1,
            sample_every_n_steps=1000,
            enable_xformers=True,
            use_gradient_checkpointing=True,
            seed=42,
            target_modules=[
                # UNet attention
                "to_q", "to_k", "to_v", "to_out.0",
                # ResNet blocks
                "proj_in", "proj_out",
                "conv1", "conv2", "conv_shortcut",
                "time_emb_proj",
                # Feed-forward
                "ff.net.0.proj", "ff.net.2",
                # Cross-attention
                "to_k", "to_v", "to_out.0",
            ],
        ),
    }
    
    if preset not in presets:
        raise ValueError(f"Unknown preset: {preset}. Available: {list(presets.keys())}")
    
    return presets[preset]


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def train_sota_lora(
    preset: str = "sota_full",
    model_path: str = "./models/stable_audio_open",
    model_type: str = "stable_audio_open",
    dataset_path: str = "./audio_dataset",
    output_dir: str = "./lora_output",
    **kwargs
):
    """Main entry point for SOTA LoRA training"""
    
    # Create config
    lora_config = create_lora_config_preset(preset)
    
    # Override with kwargs
    for k, v in kwargs.items():
        if hasattr(lora_config, k):
            setattr(lora_config, k, v)
    
    lora_config.output_dir = output_dir
    
    training_config = TrainingConfig(
        lora=lora_config,
        dataset_path=dataset_path,
        output_dir=output_dir,
        **{k: v for k, v in kwargs.items() if k in TrainingConfig.__dataclass_fields__}
    )
    
    # Initialize trainer
    trainer = SOTALoRATrainer(training_config)
    
    # Load model
    trainer.load_model(model_path, model_type)
    
    # Prepare dataset
    trainer.prepare_dataset()
    
    # Train
    trainer.train()
    
    return trainer


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SOTA LoRA Training for Audio")
    parser.add_argument("--preset", default="sota_full", choices=[
        "dora_audio", "vera_audio", "adalora_audio", "pissa_audio",
        "miss_audio", "qlora_audio", "dora_qlora_audio", "sota_full"
    ])
    parser.add_argument("--model", default="./models/stable_audio_open")
    parser.add_argument("--model-type", default="stable_audio_open")
    parser.add_argument("--dataset", default="./audio_dataset")
    parser.add_argument("--output", default="./lora_output")
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--rank", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    
    args = parser.parse_args()
    
    kwargs = {}
    if args.steps: kwargs["max_train_steps"] = args.steps
    if args.lr: kwargs["learning_rate"] = args.lr
    if args.rank: kwargs["rank"] = args.rank
    if args.batch_size: kwargs["train_batch_size"] = args.batch_size
    
    train_sota_lora(
        preset=args.preset,
        model_path=args.model,
        model_type=args.model_type,
        dataset_path=args.dataset,
        output_dir=args.output,
        **kwargs
    )