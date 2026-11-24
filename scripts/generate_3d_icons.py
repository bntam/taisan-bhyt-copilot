"""
Professional 2D/3D Medical Icon Generator for TaiSanh BHYT Clinical Copilot
Generates production-grade squircle icons with emerald-teal clinical gradients,
subtle 3D bevel lighting, embossed medical cross, and anti-aliased alpha transparency.
Outputs: 16x16, 32x32, 48x48, 128x128, 256x256, 512x512 PNGs.
"""

import os
import math
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extension", "icons")
SIZES = [16, 32, 48, 128, 256, 512]

def create_master_icon(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    margin = size * 0.06
    r = size * 0.22
    box = [margin, margin, size - margin, size - margin]

    # 1. Soft Drop Shadow
    shadow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_img)
    shadow_box = [margin, margin + size * 0.03, size - margin, size - margin + size * 0.03]
    s_draw.rounded_rectangle(shadow_box, radius=int(r), fill=(15, 23, 42, 90))
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=size * 0.035))
    img.alpha_composite(shadow_img)

    # 2. Base Squircle with Vertical Gradient (Deep Emerald -> Vibrant Teal)
    gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for y in range(int(margin), int(size - margin)):
        factor = (y - margin) / (size - 2 * margin)
        r_c = int(15 + factor * 5)
        g_c = int(118 + factor * 66)
        b_c = int(110 + factor * 56)
        line_draw = ImageDraw.Draw(gradient)
        line_draw.line([(margin, y), (size - margin, y)], fill=(r_c, g_c, b_c, 255))

    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle(box, radius=int(r), fill=255)
    gradient.putalpha(mask)
    img.alpha_composite(gradient)

    # 3. Inner 3D Highlight Ring (Top Bevel)
    inner_highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(inner_highlight)
    h_box = [margin + 4, margin + 4, size - margin - 4, size - margin - 4]
    h_draw.rounded_rectangle(h_box, radius=int(r - 2), outline=(255, 255, 255, 75), width=max(2, int(size * 0.008)))
    img.alpha_composite(inner_highlight)

    # 4. Medical Cross with 3D Emboss & Depth
    cx, cy = size / 2, size / 2
    cw = size * 0.16
    ch = size * 0.52

    # Cross shadow
    cross_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cs_draw = ImageDraw.Draw(cross_shadow)
    sy_off = size * 0.015
    cs_draw.rounded_rectangle([cx - cw/2, cy - ch/2 + sy_off, cx + cw/2, cy + ch/2 + sy_off], radius=int(cw * 0.22), fill=(10, 50, 45, 120))
    cs_draw.rounded_rectangle([cx - ch/2, cy - cw/2 + sy_off, cx + ch/2, cy + cw/2 + sy_off], radius=int(cw * 0.22), fill=(10, 50, 45, 120))
    cross_shadow = cross_shadow.filter(ImageFilter.GaussianBlur(radius=size * 0.012))
    img.alpha_composite(cross_shadow)

    # Cross base (Clean White with cream tint)
    cross_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(cross_img)
    c_draw.rounded_rectangle([cx - cw/2, cy - ch/2, cx + cw/2, cy + ch/2], radius=int(cw * 0.22), fill=(255, 255, 255, 255))
    c_draw.rounded_rectangle([cx - ch/2, cy - cw/2, cx + ch/2, cy + cw/2], radius=int(cw * 0.22), fill=(255, 255, 255, 255))

    cross_bevel = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cb_draw = ImageDraw.Draw(cross_bevel)
    inset = max(2, int(size * 0.01))
    cb_draw.rounded_rectangle([cx - cw/2 + inset, cy - ch/2 + inset, cx + cw/2 - inset, cy + ch/2 - inset], radius=int(cw * 0.18), fill=(240, 253, 250, 255))
    cb_draw.rounded_rectangle([cx - ch/2 + inset, cy - cw/2 + inset, cx + ch/2 - inset, cy + cw/2 - inset], radius=int(cw * 0.18), fill=(240, 253, 250, 255))
    
    img.alpha_composite(cross_img)
    img.alpha_composite(cross_bevel)

    # 5. Central Pulse Core Accent in Cross
    core_dot = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cd_draw = ImageDraw.Draw(core_dot)
    dot_r = size * 0.05
    cd_draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=(13, 148, 136, 230))
    cd_draw.ellipse([cx - dot_r * 0.45, cy - dot_r * 0.45, cx + dot_r * 0.45, cy + dot_r * 0.45], fill=(255, 255, 255, 240))
    img.alpha_composite(core_dot)

    return img

def generate_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    master = create_master_icon(1024)
    print("Master 1024x1024 3D medical icon rendered.")

    for s in SIZES:
        resized = master.resize((s, s), Image.Resampling.LANCZOS)
        out_path = os.path.join(OUTPUT_DIR, f"icon-{s}.png")
        resized.save(out_path, "PNG", optimize=True)
        size_kb = os.path.getsize(out_path) / 1024
        print(f"Generated: {out_path} ({s}x{s}, {size_kb:.1f} KB)")

    print("All 2D/3D medical icons successfully generated!")

if __name__ == "__main__":
    generate_all()
