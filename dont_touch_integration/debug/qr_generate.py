import qrcode

stations = ["A", "B", "C","D","E"]

for s in stations:
    img = qrcode.make(s)
    img.save(f"station_{s}.png")
