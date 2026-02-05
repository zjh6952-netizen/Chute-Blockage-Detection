import torch
import torch.nn as nn
import config_final as config

class CurvedChuteCAE(nn.Module):
    def __init__(self, feature_dim=None):
        super(CurvedChuteCAE, self).__init__()
        self.feature_dim = feature_dim or config.FEATURE_DIM
        
        # 输入改为 config.ACTIVE_SENSORS (15)
        self.encoder = nn.Sequential(
            nn.Conv1d(config.ACTIVE_SENSORS, 32, kernel_size=15, stride=2, padding=7),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=7, stride=2, padding=3),
            nn.ReLU(),
            nn.Conv1d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.ReLU()
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose1d(128, 64, kernel_size=3, stride=2, padding=1, output_padding=1),
            nn.ReLU(),
            nn.ConvTranspose1d(64, 32, kernel_size=7, stride=2, padding=3, output_padding=1),
            nn.ReLU(),
            nn.ConvTranspose1d(32, config.ACTIVE_SENSORS, kernel_size=15, stride=2, padding=7, output_padding=1),
        )

    def forward(self, x):
        input_size = x.size(-1)
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        output_size = decoded.size(-1)
        if output_size > input_size:
            diff = output_size - input_size
            start = diff // 2
            decoded = decoded[:, :, start:start + input_size]
        elif output_size < input_size:
            diff = input_size - output_size
            pad_left = diff // 2
            pad_right = diff - pad_left
            decoded = nn.functional.pad(decoded, (pad_left, pad_right), mode='replicate')
        return decoded
