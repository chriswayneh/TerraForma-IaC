Output demo.gif
Set FontSize 14
Set Width 1100
Set Height 720
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrains Mono"
Set TypingSpeed 18ms
Set Framerate 24
Set Padding 16
Set WindowBar Colorful
Set Shell bash
Hide
Type `export PATH="$TF_BIN_DIR:$PATH"`
Enter
Type `cd "$TF_DEMO_HOME"`
Enter
Type `export PS1='demo$ '`
Enter
Type `clear`
Enter
Show

Type `python -m terraforma.cli --version`
Enter
Sleep 0.8s

Type `python -m terraforma.cli doctor`
Enter
Sleep 2.0s

Type `python -m terraforma.cli describe --spec examples/aws-web.project.json`
Enter
Sleep 2.4s

Type `OUT="$(mktemp -d)" && python -m terraforma.cli generate --spec examples/aws-web.project.json --dir "$OUT" && ls "$OUT" && head -n 20 "$OUT/main.tf"`
Enter
Sleep 3.5s

Sleep 1.2s
