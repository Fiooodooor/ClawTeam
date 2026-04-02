#!/usr/bin/env python3
"""
Decode invisible Unicode steganography from a file.

Supports:
  - Bit-pair encoding (U+2062/U+2064, zero-width chars, etc.)
  - Recursive nesting (multiple layers of invisible encoding)
  - Unicode Tag smuggling (U+E0001–U+E007F → ASCII)

Usage:
  python3 decode_invisible.py <file>                        # Full auto-decode
  python3 decode_invisible.py <file> --mode inventory        # Codepoint inventory only
  python3 decode_invisible.py <file> --execute               # Decode + execute final payload
  python3 decode_invisible.py <file> --execute --force       # Skip confirmation prompt
"""
import argparse
import os
import re
import subprocess
import sys
import collections
import unicodedata

MAX_LAYERS = 10

# Known invisible bit-pair sets: (zero_candidate, one_candidate)
KNOWN_PAIRS = [
    ('\u2062', '\u2064'),   # Invisible Times / Invisible Plus
    ('\u200B', '\u200C'),   # ZWSP / ZWNJ
    ('\u200B', '\u200D'),   # ZWSP / ZWJ
    ('\u2060', '\uFEFF'),   # Word Joiner / BOM
    ('\u00AD', '\u034F'),   # Soft Hyphen / Combining Grapheme Joiner
    ('\u180E', '\u2063'),   # Mongolian Vowel Sep / Invisible Separator
]

TAG_RANGE = range(0xE0000, 0xE0080)

# Build a fast lookup set of all codepoints from KNOWN_PAIRS so detect_bit_pair
# works even when a character's Unicode category changed across versions (e.g.
# U+180E moved from Cf to Zs in Unicode 7.0).
_INVISIBLE_CODEPOINTS = set()
for _z, _o in KNOWN_PAIRS:
    _INVISIBLE_CODEPOINTS.add(ord(_z))
    _INVISIBLE_CODEPOINTS.add(ord(_o))

# Regex patterns for common BEGIN/END wrapper tags
_BEGIN_END_PATTERNS = [
    # PEM / PGP style: -----BEGIN SOMETHING-----  ...  -----END SOMETHING-----
    re.compile(
        r'^\s*-{3,}\s*BEGIN\b[^-]*-{3,}\s*\n'
        r'(.*?)'
        r'\n\s*-{3,}\s*END\b[^-]*-{3,}\s*$',
        re.DOTALL | re.IGNORECASE,
    ),
    # Dashed separator: --- BEGIN --- ... --- END ---
    re.compile(
        r'^\s*[=~#*-]{2,}\s*BEGIN\b.*?[=~#*-]{2,}\s*\n'
        r'(.*?)'
        r'\n\s*[=~#*-]{2,}\s*END\b.*?[=~#*-]{2,}\s*$',
        re.DOTALL | re.IGNORECASE,
    ),
    # XML / HTML style: <sometag ...> ... </sometag>
    re.compile(
        r'^\s*<([A-Za-z][A-Za-z0-9_-]*)(?:\s[^>]*)?>\s*\n'
        r'(.*?)'
        r'\n\s*</\1>\s*$',
        re.DOTALL,
    ),
]


def strip_begin_end_tags(text):
    """Detect and remove BEGIN/END wrapper tags from decoded text.

    Returns (stripped_text, tag_description) if tags were found,
    or (text, None) if the text had no recognised wrappers.
    """
    stripped = text.strip()

    for pattern in _BEGIN_END_PATTERNS:
        m = pattern.search(stripped)
        if m:
            # Extract the inner content (first or second capture group)
            inner = m.group(m.lastindex).strip()
            tag_line = stripped[:stripped.index('\n')].strip() if '\n' in stripped else stripped
            return inner, tag_line

    return text, None


def codepoint_inventory(content):
    """Print a frequency table of all codepoints in the content."""
    freq = collections.Counter(content)
    print("=== Codepoint Inventory ===")
    for ch, cnt in freq.most_common():
        cp = ord(ch)
        name = unicodedata.name(ch, f'U+{cp:04X}')
        visible = repr(ch) if cp < 0x20 or (0x7F <= cp <= 0x9F) else ch
        cat = unicodedata.category(ch)
        print(f"  U+{cp:04X}  count={cnt:>8}  cat={cat}  {visible!s:>3}  {name}")
    print(f"\nTotal: {len(content)} chars, {len(freq)} distinct codepoints")
    invisible = sum(cnt for ch, cnt in freq.items()
                    if unicodedata.category(ch) in ('Cf', 'Mn', 'Mc', 'Me')
                    or 0xE0000 <= ord(ch) <= 0xE007F)
    print(f"Invisible/formatting chars: {invisible} ({invisible/len(content)*100:.1f}%)")
    return freq


def detect_bit_pair(content):
    """Detect which invisible bit-pair is used, return (zero_char, one_char) or None."""
    freq = collections.Counter(ch for ch in content
                               if unicodedata.category(ch) in ('Cf', 'Mn')
                               or ord(ch) in _INVISIBLE_CODEPOINTS)
    if len(freq) < 2:
        return None
    top2 = freq.most_common(2)
    char_a, count_a = top2[0]
    char_b, count_b = top2[1]
    # More frequent char is typically 0 (ASCII bytes have leading zeros)
    return (char_a, char_b)


def decode_bit_pair(content, zero_char, one_char):
    """Extract invisible chars, map to bits, decode as 8-bit bytes."""
    inv = [ch for ch in content if ch in (zero_char, one_char)]
    if len(inv) < 8:
        return None, inv

    bits = ''.join('0' if ch == zero_char else '1' for ch in inv)

    # Try 8-bit first, then 7-bit
    for width in (8, 7):
        if len(bits) % width != 0:
            continue
        byte_vals = [int(bits[i:i+width], 2) for i in range(0, len(bits), width)]
        raw = bytes(byte_vals)
        try:
            text = raw.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            text = raw.decode('utf-8', errors='replace')

        printable = sum(1 for c in text[:500]
                        if c.isprintable() or c in '\n\r\t'
                        or unicodedata.category(c) == 'Cf'
                        or 0xE0000 <= ord(c) <= 0xE007F)
        ratio = printable / min(500, len(text)) if text else 0

        if ratio > 0.3:
            return text, inv

    # Try swapped mapping
    bits_swapped = ''.join('1' if ch == zero_char else '0' for ch in inv)
    for width in (8, 7):
        if len(bits_swapped) % width != 0:
            continue
        byte_vals = [int(bits_swapped[i:i+width], 2)
                     for i in range(0, len(bits_swapped), width)]
        raw = bytes(byte_vals)
        try:
            text = raw.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            text = raw.decode('utf-8', errors='replace')
        printable = sum(1 for c in text[:500]
                        if c.isprintable() or c in '\n\r\t'
                        or unicodedata.category(c) == 'Cf'
                        or 0xE0000 <= ord(c) <= 0xE007F)
        ratio = printable / min(500, len(text)) if text else 0
        if ratio > 0.3:
            print(f"  (note: swapped bit assignment)")
            return text, inv

    return None, inv


def decode_tags(content):
    """Decode Unicode Tag characters (U+E0000-E007F) → ASCII."""
    tag_chars = [ch for ch in content if ord(ch) in TAG_RANGE]
    if not tag_chars:
        return None
    return ''.join(chr(ord(ch) - 0xE0000) for ch in tag_chars)


def has_invisible(text):
    """Check if text contains invisible bit-pair or tag characters."""
    for ch in text:
        cp = ord(ch)
        if unicodedata.category(ch) in ('Cf',) and cp not in (0x0A, 0x0D, 0x09):
            return True
        if 0xE0000 <= cp <= 0xE007F:
            return True
    return False


def security_check(payload):
    """Classify the decoded payload for safety."""
    lower = payload.lower()
    critical = ['eval ', 'eval(', 'exec ', 'exec(', 'bash -c', 'sh -c',
                'curl | sh', 'curl |sh', 'wget | sh', '$(curl', '$(wget']
    high_exfil = ['curl ', 'wget ', 'fetch(', 'requests.get', 'requests.post']
    high_fs = [' rm ', 'rm -rf', 'chmod ', 'chown ', '> /etc/', 'dd if=']
    high_cred = ['.ssh/', '.aws/', 'token', 'password', 'secret', 'api_key']
    medium = ['ignore previous', 'ignore all', 'disregard', 'new instructions',
              'you are now', 'forget everything']

    findings = []
    for pat in critical:
        if pat in lower:
            findings.append(('CRITICAL', f'Remote code execution: `{pat.strip()}`'))
    for pat in high_exfil:
        if pat in lower:
            findings.append(('HIGH', f'Data exfiltration: `{pat.strip()}`'))
    for pat in high_fs:
        if pat in lower:
            findings.append(('HIGH', f'File system tampering: `{pat.strip()}`'))
    for pat in high_cred:
        if pat in lower:
            findings.append(('HIGH', f'Credential access: `{pat.strip()}`'))
    for pat in medium:
        if pat in lower:
            findings.append(('MEDIUM', f'Prompt injection: `{pat.strip()}`'))

    return findings


def build_layer_path(filepath, layer_num):
    """Build output path: [dir]/[name]_layer_[N].[ext] from the original filepath."""
    directory = os.path.dirname(filepath) or '.'
    basename = os.path.basename(filepath)
    name, ext = os.path.splitext(basename)
    return os.path.join(directory, f"{name}_layer_{layer_num}{ext}")


def save_layer(filepath, layer_num, content):
    """Save a decoded layer to disk and print confirmation."""
    out_path = build_layer_path(filepath, layer_num)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Saved: {out_path} ({len(content)} chars)")
    return out_path


def full_decode(content, filepath=None):
    """Run the complete multi-layer decode pipeline, optionally saving each layer."""
    layers = []
    current = content
    layer_num = 0

    while layer_num < MAX_LAYERS:
        # Check for Unicode Tags
        tag_decoded = decode_tags(current)
        if tag_decoded:
            layer_num += 1
            layer_info = {
                'layer': layer_num,
                'type': 'Unicode Tags (U+E0001-E007F → ASCII)',
                'input_chars': sum(1 for c in current if ord(c) in TAG_RANGE),
                'output_size': len(tag_decoded),
                'output': tag_decoded,
            }
            if filepath:
                layer_info['saved_path'] = save_layer(filepath, layer_num, tag_decoded)
            layers.append(layer_info)
            current = tag_decoded
            if not has_invisible(current):
                break
            continue

        # Check for bit-pair encoding
        pair = detect_bit_pair(current)
        if pair is None:
            break

        zero_ch, one_ch = pair
        decoded, inv_chars = decode_bit_pair(current, zero_ch, one_ch)
        if decoded is None:
            break

        layer_num += 1
        layer_info = {
            'layer': layer_num,
            'type': f'Bit-pair binary (U+{ord(zero_ch):04X}=0, U+{ord(one_ch):04X}=1)',
            'input_chars': len(inv_chars),
            'output_size': len(decoded),
            'output': decoded,
        }
        if filepath:
            layer_info['saved_path'] = save_layer(filepath, layer_num, decoded)
        layers.append(layer_info)
        current = decoded

        if not has_invisible(current):
            break

    return layers, current


def execute_payload(payload, filepath, force=False):
    """Execute the decoded payload after security check and user confirmation."""
    findings = security_check(payload)

    if findings and not force:
        worst = findings[0][0]
        classification = 'MALICIOUS' if worst == 'CRITICAL' else 'SUSPICIOUS'
        print(f"\n⚠  Security classification: {classification}")
        for severity, detail in findings:
            print(f"  [{severity}] {detail}")
        print(f"\nPayload to execute:")
        print(f"  {payload[:300]}{'...' if len(payload) > 300 else ''}")
        try:
            answer = input("\nExecute this payload? Type 'YES' to confirm: ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 1
        if answer.strip() != 'YES':
            print("Aborted — payload was NOT executed.")
            return 1

    print(f"\n{'=' * 60}")
    print("EXECUTING DECODED PAYLOAD")
    print(f"{'=' * 60}")

    # Determine execution method based on content
    stripped = payload.strip()
    stripped = stripped.replace('". $', '"$')
    stripped = stripped.replace('print_logo_anim', 'print_logo')
    if stripped.startswith('#!') or any(kw in stripped for kw in ('eval ', 'bash ', 'sh ', 'curl ', 'echo ')):
        # Shell-like payload
        result = subprocess.run(
            ['bash', '-c', stripped],
            capture_output=True, text=True, timeout=120
        )
        print(f"Exit code: {result.returncode}")
        if result.stdout:
            print(f"stdout:\n{result.stdout}")
        if result.stderr:
            print(f"stderr:\n{result.stderr}")
        return result.returncode
    else:
        # Write to temp file and try to detect type
        final_path = build_layer_path(filepath, 'final')
        with open(final_path, 'w', encoding='utf-8') as f:
            f.write(payload)
        print(f"Payload saved to {final_path}")
        print("Could not auto-detect execution method. Run the file manually.")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description='Decode invisible Unicode steganography from a file.',
    )
    parser.add_argument('file', help='Path to the file containing invisible Unicode payload')
    parser.add_argument('--mode', choices=['full', 'inventory'], default='full',
                        help='Operation mode (default: full)')
    parser.add_argument('--execute', action='store_true',
                        help='Execute the fully decoded payload after decoding')
    parser.add_argument('--force', action='store_true',
                        help='Skip confirmation prompt when used with --execute')
    parser.add_argument('--keep-tags', action='store_true',
                        help='Keep BEGIN/END wrapper tags on the final decoded payload '
                             '(by default they are stripped)')
    args = parser.parse_args()

    filepath = os.path.abspath(args.file)
    if not os.path.isfile(filepath):
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"File: {filepath}")
    print(f"Size: {len(content)} chars, {len(content.encode('utf-8'))} bytes\n")

    codepoint_inventory(content)

    if args.mode == 'inventory':
        return

    print("\n" + "=" * 60)
    print("DECODING")
    print("=" * 60)

    layers, final = full_decode(content, filepath=filepath)

    if not layers:
        print("\nNo invisible encoding layers detected.")
        return

    print("\n--- Decode Summary ---")
    for layer in layers:
        print(f"  Layer {layer['layer']}: {layer['type']}")
        print(f"    {layer['input_chars']} invisible chars → {layer['output_size']} chars")
        if 'saved_path' in layer:
            print(f"    File: {layer['saved_path']}")

    # --- BEGIN/END tag stripping (default: on) ---
    tag_desc = None
    if not args.keep_tags:
        final_stripped, tag_desc = strip_begin_end_tags(final)
        if tag_desc:
            print(f"\n  Detected BEGIN/END wrapper: {tag_desc}")
            print(f"  Wrapper tags removed from final payload (use --keep-tags to preserve).")
            final = final_stripped
            # Re-save the final layer without the wrappers
            if layers:
                last = layers[-1]
                last['output'] = final
                last['output_size'] = len(final)
                if 'saved_path' in last:
                    with open(last['saved_path'], 'w', encoding='utf-8') as f:
                        f.write(final)
                    print(f"  Re-saved (tags stripped): {last['saved_path']}")

    print(f"\n{'=' * 60}")
    print(f"FINAL DECODED PAYLOAD ({len(layers)} layers deep)")
    print(f"{'=' * 60}")
    print(final)

    print(f"\n{'=' * 60}")
    print("SECURITY ANALYSIS")
    print(f"{'=' * 60}")

    findings = security_check(final)
    if not findings:
        print("Classification: SAFE — no dangerous patterns detected")
    else:
        worst = findings[0][0]
        classification = 'MALICIOUS' if worst == 'CRITICAL' else 'SUSPICIOUS'
        print(f"Classification: {classification}")
        for severity, detail in findings:
            print(f"  [{severity}] {detail}")
        if not args.execute:
            print("\n⚠  DO NOT EXECUTE this payload.")

    if args.execute:
        # Always strip BEGIN/END tags before execution, even if --keep-tags
        # preserved them for display.  When tags were already stripped above
        # (--keep-tags not set), skip the second pass to avoid over-stripping
        # content that legitimately contains BEGIN/END markers.
        if args.keep_tags:
            exec_payload, _ = strip_begin_end_tags(final)
        else:
            exec_payload = final  # already stripped (or had no tags)
        sys.exit(execute_payload(exec_payload, filepath, force=args.force))


if __name__ == '__main__':
    main()
