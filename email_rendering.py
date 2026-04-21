import html as html_module
from datetime import datetime

from render_models import EmailListingViewModel

# ─── Par Avion design tokens (email-safe, mirroring the web design system) ────
#   paper      #F2E8D5   cream background
#   paper-2    #EADFC7   alt surface
#   surface    #FAF3E1   input / highlight surface
#   ink        #121212   primary text
#   ink-3      #6B6358   muted text
#   red        #B91C1C   airmail red — LP badges, CTAs, dividers
#   blue       #1E3A8A   airmail blue — CD badges only
#   border     #C9B994   thead underline
#   border-sft #DDD0B3   row dividers
#
#   Display font: Oswald → fallback "Arial Narrow", Impact, Helvetica, sans-serif
#   Body font:    Source Serif 4 → fallback Georgia, "Times New Roman", serif
#   Mono font:    JetBrains Mono → fallback "Courier New", Courier, monospace

_FONT_DISPLAY = "'Oswald','Arial Narrow',Impact,Helvetica,sans-serif"
_FONT_BODY = "'Source Serif 4',Georgia,'Times New Roman',serif"
_FONT_MONO = "'JetBrains Mono','Courier New',Courier,monospace"

# Red for LP (and any unknown/vinyl variant), blue for CD only.
_CD_BADGE_COLOR = "#1E3A8A"
_DEFAULT_BADGE_COLOR = "#B91C1C"


def _format_badge_email(fmt: str) -> str:
    if fmt == "unknown" or not fmt:
        return ""
    color = _CD_BADGE_COLOR if fmt == "CD" else _DEFAULT_BADGE_COLOR
    return (
        f'<span style="display:inline-block;background:{color};color:#F2E8D5;'
        f"font-family:{_FONT_DISPLAY};font-size:11px;font-weight:600;"
        f'letter-spacing:2px;text-transform:uppercase;padding:3px 8px;'
        f'border-radius:0;margin-left:8px;">{html_module.escape(fmt)}</span>'
    )


def _shop_block_html(shop: str, listings: list[EmailListingViewModel]) -> str:
    rows = []
    for i, lst in enumerate(listings):
        is_last = i == len(listings) - 1
        row_border = "" if is_last else "border-bottom:1px solid #DDD0B3;"
        badge = _format_badge_email(lst.format)

        meta_parts = []
        if lst.signed_by != "unknown":
            meta_parts.append(f"signed by: {lst.signed_by}")
        if lst.signature_location != "unknown":
            meta_parts.append(f"location: {lst.signature_location}")
        meta_str = "  ·  ".join(meta_parts)
        meta_html = (
            f'<div style="font-family:{_FONT_MONO};font-size:12px;line-height:18px;'
            f'color:#6B6358;margin-top:4px;">{html_module.escape(meta_str)}</div>'
            if meta_str
            else ""
        )

        alt_text = (
            f"{lst.title} by {lst.artist}"
            if lst.artist and lst.artist.lower() != "unknown"
            else lst.title
        )
        img_cell = (
            f'<td width="64" style="padding:14px 12px 14px 0;vertical-align:middle;width:64px;">'
            f'<img src="{html_module.escape(lst.image_url)}" width="52" height="52" '
            f'alt="{html_module.escape(alt_text)}" '
            f'style="display:block;border:1px solid #121212;border-radius:0;'
            f'width:52px;height:52px;object-fit:cover;"></td>'
            if lst.image_url
            else (
                '<td width="64" style="padding:14px 12px 14px 0;vertical-align:middle;width:64px;">'
                '<div role="presentation" aria-hidden="true" '
                'style="width:52px;height:52px;background:#EADFC7;border:1px solid #C9B994;"></div>'
                '</td>'
            )
        )

        # Bulletproof Buy button — VML for Outlook + HTML for everyone else.
        buy_block = ""
        if lst.url:
            buy_href = html_module.escape(lst.url)
            buy_block = f"""
                <!--[if mso]>
                <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml"
                  xmlns:w="urn:schemas-microsoft-com:office:word"
                  href="{buy_href}"
                  style="height:30px;v-text-anchor:middle;width:82px;"
                  arcsize="0%" strokecolor="#B91C1C" strokeweight="1.5pt"
                  fillcolor="#F2E8D5">
                  <w:anchorlock/>
                  <center style="color:#B91C1C;font-family:Arial,sans-serif;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;">Buy now</center>
                </v:roundrect>
                <![endif]-->
                <!--[if !mso]><!-->
                <a href="{buy_href}"
                   style="display:inline-block;font-family:{_FONT_DISPLAY};
                   font-size:12px;font-weight:600;letter-spacing:2px;
                   text-transform:uppercase;color:#B91C1C;text-decoration:none;
                   border:1.5px solid #B91C1C;padding:6px 14px;border-radius:0;
                   background-color:#F2E8D5;mso-hide:all;">Buy now</a>
                <!--<![endif]-->"""

        price_html = (
            f'<div style="font-family:{_FONT_DISPLAY};font-size:15px;font-weight:600;'
            f'color:#121212;letter-spacing:-0.01em;margin-bottom:6px;'
            f'white-space:nowrap;">{html_module.escape(lst.price)}</div>'
            if lst.price
            else ""
        )

        rows.append(f"""
          <tr>
            {img_cell}
            <td style="padding:14px 12px;vertical-align:middle;{row_border}">
              <div style="font-family:{_FONT_BODY};font-size:16px;line-height:22px;
                   font-weight:400;color:#121212;">{html_module.escape(lst.title)}{badge}</div>
              <div style="font-family:{_FONT_MONO};font-size:13px;line-height:19px;
                   color:#6B6358;margin-top:4px;letter-spacing:0.02em;">{html_module.escape(lst.artist)}</div>
              {meta_html}
            </td>
            <td style="padding:14px 0 14px 12px;vertical-align:middle;text-align:right;
                white-space:nowrap;{row_border}">
              {price_html}
              {buy_block}
            </td>
          </tr>""")

    count_label = f"{len(listings)} listing{'s' if len(listings) != 1 else ''}"
    return f"""
      <tr>
        <td style="padding:32px 24px 0 24px;">
          <h2 style="mso-line-height-rule:exactly;margin:0;padding-bottom:10px;
              border-bottom:1.5px solid #B91C1C;font-family:{_FONT_DISPLAY};
              font-size:22px;line-height:26px;letter-spacing:2px;font-weight:600;
              color:#121212;text-transform:uppercase;">{html_module.escape(shop)}</h2>
          <div style="font-family:{_FONT_MONO};font-size:12px;line-height:18px;
               letter-spacing:2px;color:#6B6358;text-transform:uppercase;
               margin-top:6px;">{count_label}</div>
          <table role="presentation" cellpadding="0" cellspacing="0" border="0"
                 width="100%" style="width:100%;border-collapse:collapse;margin-top:4px;">
            {"".join(rows)}
          </table>
        </td>
      </tr>"""


def build_email_html(new_listings: list[EmailListingViewModel]) -> str:
    by_shop: dict[str, list[EmailListingViewModel]] = {}
    for lst in new_listings:
        by_shop.setdefault(lst.shop, []).append(lst)

    shops_html = "".join(
        _shop_block_html(shop, by_shop[shop]) for shop in sorted(by_shop)
    )
    now = datetime.now()
    count = len(new_listings)
    count_word = f"{count} new listing{'s' if count != 1 else ''}"
    preview = (
        f"{count_word} across {len(by_shop)} shop"
        f"{'s' if len(by_shop) != 1 else ''} — scanned "
        f"{now.strftime('%b %d, %I:%M %p')}."
    )

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<title>Dispatches — Autograph Notifier</title>
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings>
  <o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings></xml></noscript>
<![endif]-->
<style type="text/css">
  body, table, td, a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
  img {{ -ms-interpolation-mode:bicubic; border:0; display:block; outline:none; text-decoration:none; }}
  body {{ margin:0 !important; padding:0 !important; width:100% !important; background-color:#F2E8D5; }}
  a[x-apple-data-detectors] {{ color:inherit !important; text-decoration:none !important; }}
  u + #body a {{ color:inherit; text-decoration:none; }}
  @media screen and (max-width:600px) {{
    .email-container {{ width:100% !important; max-width:100% !important; }}
    .mobile-pad {{ padding-left:20px !important; padding-right:20px !important; }}
    .mobile-title {{ font-size:16px !important; line-height:22px !important; }}
    .mobile-meta {{ font-size:14px !important; line-height:20px !important; }}
    .mobile-h1   {{ font-size:26px !important; line-height:30px !important; }}
    .mobile-h2   {{ font-size:20px !important; line-height:24px !important; }}
  }}
</style>
</head>
<body id="body" style="margin:0;padding:0;background-color:#F2E8D5;">

<span style="display:none;max-height:0;overflow:hidden;mso-hide:all;
     font-size:1px;color:#F2E8D5;line-height:1px;opacity:0;">
  {html_module.escape(preview)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
</span>

<table role="presentation" cellpadding="0" cellspacing="0" border="0"
       width="100%" style="background-color:#F2E8D5;">
  <tr>
    <td align="center" style="padding:24px 12px;">

      <table role="presentation" class="email-container" cellpadding="0" cellspacing="0"
             border="0" width="600"
             style="max-width:600px;width:100%;background-color:#F2E8D5;
                    border:1px solid #121212;">

        <tr>
          <td class="mobile-pad" style="padding:28px 24px 18px 24px;border-bottom:1px solid #121212;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td style="vertical-align:middle;">
                  <h1 class="mobile-h1" style="mso-line-height-rule:exactly;margin:0;
                      font-family:{_FONT_DISPLAY};font-size:28px;line-height:32px;
                      font-weight:600;letter-spacing:4px;text-transform:uppercase;
                      color:#121212;">
                    Autograph&nbsp;<span style="color:#B91C1C;">Notifier</span>
                  </h1>
                  <div style="font-family:{_FONT_MONO};font-size:11px;line-height:16px;
                       letter-spacing:2px;text-transform:uppercase;color:#6B6358;
                       margin-top:8px;">Signed &middot; Sealed &middot; Delivered</div>
                </td>
                <td align="right" style="vertical-align:middle;white-space:nowrap;
                    padding-left:12px;">
                  <div style="display:inline-block;border:1.5px solid #B91C1C;padding:4px 10px;
                       font-family:{_FONT_DISPLAY};font-size:11px;font-weight:600;
                       letter-spacing:3px;text-transform:uppercase;color:#B91C1C;
                       background-color:#F2E8D5;">Dispatch</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td class="mobile-pad" style="padding:20px 24px 8px 24px;">
            <div style="font-family:{_FONT_DISPLAY};font-size:15px;line-height:20px;
                 font-weight:600;letter-spacing:2px;text-transform:uppercase;
                 color:#121212;">{html_module.escape(count_word)}</div>
            <div style="font-family:{_FONT_MONO};font-size:12px;line-height:18px;
                 letter-spacing:1px;color:#6B6358;margin-top:4px;">
              Scanned {html_module.escape(now.strftime('%B %d, %Y at %I:%M %p'))}
            </div>
          </td>
        </tr>

        {shops_html}

        <tr>
          <td class="mobile-pad" style="padding:32px 24px;border-top:1px solid #C9B994;
              text-align:center;">
            <div style="font-family:{_FONT_MONO};font-size:11px;line-height:18px;
                 letter-spacing:3px;text-transform:uppercase;color:#6B6358;">
              Autograph Notifier &middot; Automated Dispatch
            </div>
            <div style="font-family:{_FONT_BODY};font-size:13px;line-height:19px;
                 color:#6B6358;margin-top:10px;font-style:italic;">
              You're receiving this because you asked to be notified about newly signed vinyl &amp; CDs.
            </div>
          </td>
        </tr>

      </table>

    </td>
  </tr>
</table>
</body>
</html>"""
