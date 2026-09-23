"""Graphical rank card generation for Odinus profiles."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from odinus.services.perfil import ProfileData


WIDTH = 1400
HEIGHT = 600

BACKGROUND = (15, 17, 23)
CARD = (24, 27, 35)
CARD_LIGHT = (32, 36, 46)

# Lime green accent.
ACCENT = (170, 255, 0)

TEXT = (245, 247, 250)
MUTED = (160, 166, 178)
PROGRESS_BG = (53, 57, 69)

AVATAR_SIZE = 230

EMOJI_FONT_PATH = Path(
    "C:/Windows/Fonts/seguiemj.ttf"
)


def _font(
    size: int,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a Windows or Linux system font."""
    candidates = (
        [
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/segoeuib.ttf"),
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),
        ]
        if bold
        else [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans.ttf"
            ),
        ]
    )

    for path in candidates:
        if path.exists():
            return ImageFont.truetype(
                str(path),
                size,
            )

    return ImageFont.load_default()


def _emoji_font(
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the Windows emoji font."""
    if EMOJI_FONT_PATH.exists():
        return ImageFont.truetype(
            str(EMOJI_FONT_PATH),
            size,
        )

    return _font(size)


def _draw_emoji_text(
    draw: ImageDraw.ImageDraw,
    emoji: str,
    text: str,
    position: tuple[int, int],
    text_font: ImageFont.ImageFont,
    emoji_size: int,
    fill: tuple[int, int, int],
) -> None:
    """Draw an emoji with Segoe UI Emoji followed by normal text."""
    x, y = position

    emoji_font = _emoji_font(emoji_size)

    draw.text(
        (x, y),
        emoji,
        font=emoji_font,
        fill=fill,
    )

    emoji_bbox = draw.textbbox(
        (x, y),
        emoji,
        font=emoji_font,
    )

    emoji_width = (
        emoji_bbox[2]
        - emoji_bbox[0]
    )

    draw.text(
        (
            x + emoji_width + 8,
            y,
        ),
        text,
        font=text_font,
        fill=fill,
    )


def _draw_emoji_only(
    draw: ImageDraw.ImageDraw,
    emoji: str,
    position: tuple[int, int],
    emoji_size: int,
    fill: tuple[int, int, int],
) -> None:
    """Draw an emoji using Segoe UI Emoji."""
    draw.text(
        position,
        emoji,
        font=_emoji_font(emoji_size),
        fill=fill,
    )


def _draw_reward(
    draw: ImageDraw.ImageDraw,
    reward_name: str,
    position: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    """Draw the reward name without Discord emojis or decorations."""
    x, y = position

    clean_name = reward_name.strip()

    # Existing Discord roles may still contain:
    # 『🍊』NIVEL 60
    #
    # Remove everything before the closing decorative bracket
    # so the rank card only displays:
    # NIVEL 60
    if "』" in clean_name:
        clean_name = clean_name.split(
            "』",
            1,
        )[1].strip()

    draw.text(
        (x, y),
        clean_name,
        font=font,
        fill=fill,
    )


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    maximum_width: int,
) -> str:
    """Shorten text until it fits inside a maximum width."""
    if draw.textbbox(
        (0, 0),
        text,
        font=font,
    )[2] <= maximum_width:
        return text

    while len(text) > 1:
        text = text[:-2] + "…"

        if draw.textbbox(
            (0, 0),
            text,
            font=font,
        )[2] <= maximum_width:
            return text

    return text


def _rounded_avatar(
    avatar_bytes: bytes,
) -> Image.Image:
    """Convert avatar bytes into a circular image."""
    avatar = Image.open(
        BytesIO(avatar_bytes)
    ).convert("RGB")

    avatar = avatar.resize(
        (AVATAR_SIZE, AVATAR_SIZE),
        Image.Resampling.LANCZOS,
    )

    mask = Image.new(
        "L",
        (AVATAR_SIZE, AVATAR_SIZE),
        0,
    )

    mask_draw = ImageDraw.Draw(mask)

    mask_draw.ellipse(
        (0, 0, AVATAR_SIZE, AVATAR_SIZE),
        fill=255,
    )

    result = Image.new(
        "RGB",
        (AVATAR_SIZE, AVATAR_SIZE),
    )

    result.paste(
        avatar,
        (0, 0),
        mask,
    )

    return result


def _draw_card(
    profile: ProfileData,
    avatar_bytes: bytes,
) -> BytesIO:
    """Render the complete rank card."""
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BACKGROUND,
    )

    draw = ImageDraw.Draw(image)

    font_name = _font(48, bold=True)
    font_username = _font(24)
    font_level = _font(38, bold=True)
    font_stat = _font(24)
    font_small = _font(20)
    font_footer = _font(18)

    # Main card.
    draw.rounded_rectangle(
        (20, 20, WIDTH - 20, HEIGHT - 20),
        radius=36,
        fill=CARD,
    )

    # Accent strip.
    draw.rounded_rectangle(
        (20, 20, 34, HEIGHT - 20),
        radius=7,
        fill=ACCENT,
    )

    # Decorative circles.
    draw.ellipse(
        (
            WIDTH - 280,
            -120,
            WIDTH + 100,
            260,
        ),
        fill=(25, 45, 22),
    )

    draw.ellipse(
        (
            WIDTH - 130,
            380,
            WIDTH + 180,
            690,
        ),
        fill=(27, 29, 38),
    )

    # Avatar.
    avatar = _rounded_avatar(
        avatar_bytes
    )

    avatar_x = 70
    avatar_y = 75

    draw.ellipse(
        (
            avatar_x - 8,
            avatar_y - 8,
            avatar_x + AVATAR_SIZE + 8,
            avatar_y + AVATAR_SIZE + 8,
        ),
        fill=ACCENT,
    )

    image.paste(
        avatar,
        (avatar_x, avatar_y),
    )

    # Identity.
    content_x = 350

    display_name = _fit_text(
        draw,
        profile.member.display_name,
        font_name,
        700,
    )

    draw.text(
        (content_x, 65),
        display_name,
        font=font_name,
        fill=TEXT,
    )

    username = f"@{profile.member.name}"

    username = _fit_text(
        draw,
        username,
        font_username,
        650,
    )

    draw.text(
        (content_x, 125),
        username,
        font=font_username,
        fill=MUTED,
    )

    # Level.
    draw.text(
        (content_x, 175),
        f"NIVEL {profile.level.level}",
        font=font_level,
        fill=ACCENT,
    )

    # Ranking.
    ranking_x = content_x + 250

    _draw_emoji_only(
        draw,
        "🏆",
        (ranking_x, 180),
        24,
        TEXT,
    )

    draw.text(
        (ranking_x + 34, 182),
        (
            f"#{profile.rank}"
            if profile.rank > 0
            else "—"
        ),
        font=font_stat,
        fill=TEXT,
    )

    # XP.
    if profile.level.level >= 1000:
        xp_current = 0
        xp_required = 0
        percentage = 100.0

        xp_text = (
            f"{profile.level.total_xp:,} XP • "
            "NIVEL MÁXIMO"
        )

    else:
        from odinus.services.niveles import LevelService

        level_service = LevelService()

        xp_current, xp_required = (
            level_service.xp_progress(
                profile.level.total_xp
            )
        )

        percentage = (
            xp_current / xp_required * 100
            if xp_required > 0
            else 0
        )

        xp_text = (
            f"{xp_current:,} / "
            f"{xp_required:,} XP"
        )

    draw.text(
        (content_x, 235),
        xp_text,
        font=font_stat,
        fill=TEXT,
    )

    percentage = max(
        0,
        min(100, percentage),
    )

    percentage_text = f"{percentage:.1f}%"

    percentage_bbox = draw.textbbox(
        (0, 0),
        percentage_text,
        font=font_small,
    )

    draw.text(
        (
            WIDTH - 80 - (
                percentage_bbox[2]
                - percentage_bbox[0]
            ),
            235,
        ),
        percentage_text,
        font=font_small,
        fill=MUTED,
    )

    # XP bar.
    bar_x1 = content_x
    bar_y1 = 275
    bar_x2 = WIDTH - 80
    bar_y2 = 310

    draw.rounded_rectangle(
        (
            bar_x1,
            bar_y1,
            bar_x2,
            bar_y2,
        ),
        radius=17,
        fill=PROGRESS_BG,
    )

    fill_width = int(
        (bar_x2 - bar_x1)
        * percentage
        / 100
    )

    if fill_width > 0:
        draw.rounded_rectangle(
            (
                bar_x1,
                bar_y1,
                bar_x1 + fill_width,
                bar_y2,
            ),
            radius=17,
            fill=ACCENT,
        )

    # Information panels.
    panel_y = 355

    panel_width = 235
    panel_height = 105
    gap = 18

    panels = [
        (
            "🌎",
            "País",
            profile.country or "No configurado",
        ),
        (
            "🔞",
            "Edad",
            profile.age or "No configurada",
        ),
        (
            "🎂",
            "Cumpleaños",
            profile.birthday or "No registrado",
        ),
        (
            "📨",
            "Invitaciones",
            str(profile.invitations),
        ),
    ]

    for index, (emoji, label, value) in enumerate(
        panels
    ):
        x = 70 + index * (
            panel_width + gap
        )

        draw.rounded_rectangle(
            (
                x,
                panel_y,
                x + panel_width,
                panel_y + panel_height,
            ),
            radius=18,
            fill=CARD_LIGHT,
        )

        _draw_emoji_text(
            draw,
            emoji,
            label,
            (x + 18, panel_y + 15),
            font_small,
            20,
            MUTED,
        )

        value = _fit_text(
            draw,
            value,
            font_stat,
            panel_width - 36,
        )

        draw.text(
            (x + 18, panel_y + 53),
            value,
            font=font_stat,
            fill=TEXT,
        )

    # Joined date.
    if profile.joined_at is not None:
        joined_text = profile.joined_at.strftime(
            "%d/%m/%Y"
        )
    else:
        joined_text = "Desconocida"

    _draw_emoji_text(
        draw,
        "📅",
        f"Miembro desde: {joined_text}",
        (70, 490),
        font_small,
        20,
        MUTED,
    )

    # Current reward.
    draw.text(
        (720, 490),
        "Recompensa",
        font=font_small,
        fill=MUTED,
    )

    if profile.reward_name is not None:
        _draw_reward(
            draw,
            profile.reward_name,
            (720, 520),
            font_stat,
            TEXT,
        )
    else:
        draw.text(
            (720, 520),
            "Sin recompensa",
            font=font_stat,
            fill=TEXT,
        )

    # Footer.
    footer = "ODINUS • PERFIL"

    footer_bbox = draw.textbbox(
        (0, 0),
        footer,
        font=font_footer,
    )

    draw.text(
        (
            WIDTH - 70 - (
                footer_bbox[2]
                - footer_bbox[0]
            ),
            HEIGHT - 52,
        ),
        footer,
        font=font_footer,
        fill=MUTED,
    )

    output = BytesIO()

    image.save(
        output,
        format="PNG",
        optimize=True,
    )

    output.seek(0)

    return output


async def generate_rank_card(
    profile: ProfileData,
) -> BytesIO:
    """Generate the rank card without blocking Discord's event loop."""
    avatar_bytes = await profile.member.display_avatar.read()

    return await asyncio.to_thread(
        _draw_card,
        profile,
        avatar_bytes,
    )