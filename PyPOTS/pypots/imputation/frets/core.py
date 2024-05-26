"""
The core wrapper assembles the submodules of FreTS imputation model
and takes over the forward progress of the algorithm.
"""

# Created by Wenjie Du <wenjay.du@gmail.com>
# License: BSD-3-Clause

import torch.nn as nn

from ...nn.modules.frets import BackboneFreTS
from ...nn.modules.saits import SaitsLoss, SaitsEmbedding


class _FreTS(nn.Module):
    def __init__(
        self,
        n_steps,
        n_features,
        embed_size: int = 128,  # the default value is the same as the fixed one in the original implementation
        hidden_size: int = 256,  # the default value is the same as the fixed one in the original implementation
        channel_independence: bool = False,
        ORT_weight: float = 1,
        MIT_weight: float = 1,
    ):
        super().__init__()

        self.n_steps = n_steps

        self.saits_embedding = SaitsEmbedding(
            n_features * 2,
            embed_size,
            with_pos=False,
        )
        self.backbone = BackboneFreTS(
            n_steps,
            n_features,
            embed_size,
            n_steps,
            hidden_size,
            channel_independence,
        )

        # for the imputation task, the output dim is the same as input dim
        self.output_projection = nn.Linear(embed_size, n_features)
        self.saits_loss_func = SaitsLoss(ORT_weight, MIT_weight)

    def forward(self, inputs: dict, training: bool = True) -> dict:
        X, missing_mask = inputs["X"], inputs["missing_mask"]

        # WDU: the original FreTS paper isn't proposed for imputation task. Hence the model doesn't take
        # the missing mask into account, which means, in the process, the model doesn't know which part of
        # the input data is missing, and this may hurt the model's imputation performance. Therefore, I apply the
        # SAITS embedding method to project the concatenation of features and masks into a hidden space, as well as
        # the output layers to project back from the hidden space to the original space.
        enc_out = self.saits_embedding(X, missing_mask)

        # FreTS processing
        backbone_output = self.backbone(enc_out)
        reconstruction = self.output_projection(backbone_output)

        imputed_data = missing_mask * X + (1 - missing_mask) * reconstruction
        results = {
            "imputed_data": imputed_data,
        }

        # if in training mode, return results with losses
        if training:
            X_ori, indicating_mask = inputs["X_ori"], inputs["indicating_mask"]
            loss, ORT_loss, MIT_loss = self.saits_loss_func(
                reconstruction, X_ori, missing_mask, indicating_mask
            )
            results["ORT_loss"] = ORT_loss
            results["MIT_loss"] = MIT_loss
            # `loss` is always the item for backward propagating to update the model
            results["loss"] = loss

        return results
