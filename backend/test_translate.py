"""Quick CLI test: translate one image through the running backend.
Usage:  venv/Scripts/python.exe test_translate.py <input_image> [output.png]
"""
import sys, json, base64, urllib.request, time, uuid

src = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/srira/Downloads/01.jpg"
out = sys.argv[2] if len(sys.argv) > 2 else "translated.png"

img = open(src, "rb").read()
b = uuid.uuid4().hex
body = (
    f'--{b}\r\nContent-Disposition: form-data; name="file"; '
    f'filename="x.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
).encode() + img + f"\r\n--{b}--\r\n".encode()

req = urllib.request.Request(
    "http://127.0.0.1:8000/translate-image",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={b}"},
)
t = time.time()
d = json.loads(urllib.request.urlopen(req, timeout=300).read())
print(f"done in {time.time()-t:.1f}s  |  {len(d['regions'])} bubbles")
for r in d["regions"]:
    print("  -", (r["translated_text"] or "").replace("\n", " ")[:60])
if d.get("glossary"):
    print("glossary:", ", ".join(f"{k}={v}" for k, v in d["glossary"].items()))
open(out, "wb").write(base64.b64decode(d["rendered_image"].split(",", 1)[1]))
print("wrote", out)
