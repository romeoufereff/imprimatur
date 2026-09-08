"""Assemble final SVG document."""


def svg(width, height, defs="", body="", bg=None, view=None):
    vb = view or f"0 0 {width} {height}"
    rect = f'<rect width="100%" height="100%" fill="{bg}"/>' if bg else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="{vb}">'
        f"<defs>{defs}</defs>{rect}{body}</svg>"
    )


def fragment(defs="", body=""):
    """Return (defs, body) unwrapped — for embedding directly inside an
    host slide's own <svg viewBox="..." style="width:100%;flex:1"> element
    instead of producing a standalone document. This is the usual path when
    deck-designer drops a reconstructed diagram straight into a template's
    content area rather than importing a separate <svg> file."""
    return defs, body
