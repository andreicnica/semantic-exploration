from torchvision import models
import torch
import torch.nn as nn
from torchsummary import summary


def conv_relu(in_channels, out_channels, kernel, padding):
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels, kernel, padding=padding),
        nn.ReLU(inplace=True),
    )


class ResNetUNet(nn.Module):

    def __init__(self, cfg, no_classes=80):
        super().__init__()

        self.base_model = base_model = models.resnet18(pretrained=True)

        self.base_layers = list(base_model.children())

        # --- Other inputs
        in_channels = 3
        factor_in = 64
        self.layer1_pre = conv_relu(in_channels, factor_in, 1, 0)
        self.layer1_in = conv_relu(factor_in + 64, 64, 1, 0)
        self.layer2_pre = conv_relu(in_channels, factor_in, 1, 0)
        self.layer2_in = conv_relu(factor_in + 64, 64, 1, 0)
        self.layer3_pre = conv_relu(in_channels, factor_in, 1, 0)
        self.layer3_in = conv_relu(factor_in + 128, 128, 1, 0)

        self.layer0 = nn.Sequential(*self.base_layers[:3])  # size=(N, 64, x.H/2, x.W/2)
        self.layer0_1x1 = conv_relu(64, 64, 1, 0)
        self.layer1 = nn.Sequential(*self.base_layers[3:5])  # size=(N, 64, x.H/4, x.W/4)
        self.layer1_1x1 = conv_relu(64, 64, 1, 0)
        self.layer2 = self.base_layers[5]  # size=(N, 128, x.H/8, x.W/8)
        self.layer2_1x1 = conv_relu(128, 128, 1, 0)
        self.layer3 = self.base_layers[6]  # size=(N, 256, x.H/16, x.W/16)
        self.layer3_1x1 = conv_relu(256, 256, 1, 0)
        self.layer4 = self.base_layers[7]  # size=(N, 512, x.H/32, x.W/32)
        self.layer4_1x1 = conv_relu(512, 512, 1, 0)

        self.upsample = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)

        self.conv_up3 = conv_relu(256 + 512, 512, 3, 1)
        self.conv_up2 = conv_relu(128 + 512, 256, 3, 1)
        self.conv_up1 = conv_relu(64 + 256, 256, 3, 1)
        self.conv_up0 = conv_relu(64 + 256, 256, 3, 1)

        self.conv_up3_reg = nn.Dropout2d(0.3, inplace=True)  # nn.BatchNorm2d(256 + 512)
        self.conv_up2_reg = nn.Dropout2d(0.3, inplace=True)  # nn.BatchNorm2d(128 + 512)
        self.conv_up1_reg = nn.Dropout2d(0.3, inplace=True)  # nn.BatchNorm2d(64 + 256)
        self.conv_up0_reg = nn.Dropout2d(0.3, inplace=True)  # nn.BatchNorm2d(64 + 256)

        self.conv_original_size0 = conv_relu(3, 64, 3, 1)
        self.conv_original_size1 = conv_relu(64, 64, 3, 1)
        self.conv_original_size2 = conv_relu(64 + 256, 256, 3, 1)

        self.conv_last = nn.Conv2d(256, no_classes, 1)

    def forward(self, input):
        input0, input1, input2, input3 = input

        # -- Reduce 2D dimensionality
        layer0 = self.layer0(input0)  # in 256, 256

        # ==========================================================================================
        # -- Add smaller input
        input1 = self.layer1_pre(input1)  # out 64, 128, 128
        layer0 = torch.cat([input1, layer0], dim=1)  # 128+64, 128, 128
        layer0 = self.layer1_in(layer0)
        # ==========================================================================================

        layer1 = self.layer1(layer0)  # in 128, 128, 128

        # ==========================================================================================
        # -- Add smaller input
        input2 = self.layer2_pre(input2)  # out 64, 128, 128
        layer1 = torch.cat([input2, layer1], dim=1)  # 128+64, 128, 128
        layer1 = self.layer2_in(layer1)
        # ==========================================================================================

        layer2 = self.layer2(layer1)  # in 256, 64, 64

        # ==========================================================================================
        # -- Add smaller input
        input3 = self.layer3_pre(input3)  # out 64, 128, 128
        layer2 = torch.cat([input3, layer2], dim=1)  # 128+64, 128, 128
        layer2 = self.layer3_in(layer2)
        # ==========================================================================================

        layer3 = self.layer3(layer2)  # in 32, 32
        layer4 = self.layer4(layer3)  # in 16, 16

        layer4 = self.layer4_1x1(layer4)  # in 8, 8

        x = self.upsample(layer4)
        layer3 = self.layer3_1x1(layer3)
        x = torch.cat([x, layer3], dim=1)
        x = self.conv_up3_reg(x)
        x = self.conv_up3(x)

        x = self.upsample(x)
        layer2 = self.layer2_1x1(layer2)
        x = torch.cat([x, layer2], dim=1)
        x = self.conv_up2_reg(x)
        x = self.conv_up2(x)

        x = self.upsample(x)
        layer1 = self.layer1_1x1(layer1)
        x = torch.cat([x, layer1], dim=1)
        x = self.conv_up1_reg(x)
        x = self.conv_up1(x)

        x = self.upsample(x)
        layer0 = self.layer0_1x1(layer0)
        x = torch.cat([x, layer0], dim=1)
        x = self.conv_up0_reg(x)
        x = self.conv_up0(x)

        x = self.upsample(x)
        x_original = self.conv_original_size0(input0)
        x_original = self.conv_original_size1(x_original)
        x = torch.cat([x, x_original], dim=1)
        x = self.conv_original_size2(x)

        out = self.conv_last(x)

        return out


if __name__ == "__main__":
    net = ResNetUNet(80)
    device = "cuda:0"
    net = net.to(device)

    for i in range(300):
        x0 = torch.rand(1, 3, 256, 256).to(device)
        x1 = torch.rand(1, 3, 128, 128).to(device)
        x2 = torch.rand(1, 3, 64, 64).to(device)
        x3 = torch.rand(1, 3, 32, 32).to(device)

        out = net((x0, x1, x2, x3))
