"""The QR block printed under the disclaimer when the prescription has a private download link. Pure."""
import segno

from .sections import esc


def qr_data_uri(url: str) -> str:
    """The QR for ``url`` as an SVG data URI; the same URL always gives the same image."""
    return segno.make(url, error="m", micro=False).svg_data_uri(scale=4, border=2)


def share_block(share) -> str:
    """``share`` is ``meta["share"]``: ``{"url", "until"}``. Anything else prints nothing."""
    if not isinstance(share, dict) or not share.get("url"):
        return ""
    return (
        '<div class="share-qr" style="text-align:right;margin-top:4mm;break-inside:avoid">'
        f'<img src="{esc(qr_data_uri(share["url"]))}" alt="" style="width:22mm;height:22mm">'
        f'<div style="font-size:9px;color:#333">Scan to download · valid until {esc(share.get("until"))}</div></div>'
    )
