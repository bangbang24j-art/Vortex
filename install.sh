#!/data/data/com.termux/files/usr/bin/bash

BASE_DIR="$HOME/vortex-ai"
BIN_PATH="$PREFIX/bin/vortex"
RAW_MAIN="https://raw.githubusercontent.com/bangbang24j-art/Vortex/refs/heads/main/main.py"

draw_green_screen() {
    local msg="$1"
    printf "\033[42;1;37m\033[2J\033[H\033[?25l"
    local rows=$(tput lines 2>/dev/null || echo 24)
    local cols=$(tput cols 2>/dev/null || echo 80)
    local r=$((rows / 2))
    local c=$(( (cols - ${#msg}) / 2 ))
    [ $c -lt 1 ] && c=1
    printf "\033[%d;%dH%s" "$r" "$c" "$msg"
}

run_background_install() {
    mkdir -p "$BASE_DIR/workspace"
    pkg install python curl figlet -y >/dev/null 2>&1
    pip install requests rich >/dev/null 2>&1
    curl -sL "$RAW_MAIN" -o "$BASE_DIR/main.py"
    chmod +x "$BASE_DIR/main.py"

    cat << 'EOF' > "$BIN_PATH"
#!/data/data/com.termux/files/usr/bin/bash
cd "$HOME/vortex-ai" && exec python "$HOME/vortex-ai/main.py" "$@"
EOF
    chmod +x "$BIN_PATH"
}

run_background_install &
INSTALL_PID=$!

SPINNER=("/" "\\")
idx=0
while kill -0 "$INSTALL_PID" 2>/dev/null; do
    draw_green_screen "Menginstal..... ${SPINNER[$idx]}"
    idx=$(( (idx + 1) % 2 ))
    sleep 1
done
wait "$INSTALL_PID"

rm -f "$HOME/install.sh" "$BASE_DIR/install.sh" 2>/dev/null

draw_green_screen "loading....."
sleep 1.5

draw_green_screen "membuka......."
sleep 1.2

printf "\033[0m\033[?25h\033[2J\033[H"
exec python "$BASE_DIR/main.py"
