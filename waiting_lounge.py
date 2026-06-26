import json

import streamlit as st
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval

from i18n import t
from utils import guvenli_metin


def sayfa_ustune_hizala(component_key: str) -> None:
    streamlit_js_eval(
        js_expressions="""
        (() => {
            setFrameHeight(0);
            const doc = window.parent.document;
            const main = doc.querySelector('[data-testid="stMain"]');
            const shell = doc.querySelector('.sb-lounge-shell');
            if (main && shell) {
                const shellTop = shell.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop;
                main.scrollTo({ top: Math.max(0, shellTop - 56), left: 0, behavior: "auto" });
            }
            return true;
        })()
        """,
        key=component_key,
        default=False,
        want_output=False,
    )


def bekleme_salonu_ciz() -> None:
    labels = {
        "title": t("lounge.title"),
        "subtitle": t("lounge.subtitle"),
        "gameTitle": t("lounge.game_title"),
        "level": t("lounge.level"),
        "charge": t("lounge.charge"),
        "best": t("lounge.best"),
        "start": t("lounge.start"),
        "restart": t("lounge.restart"),
        "ready": t("lounge.ready"),
        "crashed": t("lounge.crashed"),
        "complete": t("lounge.complete"),
        "finished": t("lounge.finished"),
        "tap": t("lounge.tap"),
    }
    labels_json = json.dumps(labels, ensure_ascii=False).replace("</", "<\\/")
    game_html = """
        <section class="sb-lounge-game" aria-label="__LOUNGE_ARIA__">
            <div class="sb-lounge-head">
                <div>
                    <span>__GAME_TITLE__</span>
                    <strong id="levelLabel">__LEVEL_LABEL__ 01</strong>
                </div>
                <div class="sb-lounge-meter">
                    <small id="chargeText">__CHARGE_LABEL__ 0%</small>
                    <i><b id="chargeFill"></b></i>
                </div>
            </div>
            <div class="sb-game-stage">
                <canvas id="voltGame" width="360" height="430" tabindex="0"></canvas>
                <div class="sb-game-overlay" id="overlay">
                    <strong id="overlayTitle">__READY_LABEL__</strong>
                    <button id="startButton" type="button">__START_LABEL__</button>
                </div>
            </div>
            <div class="sb-lounge-controls" aria-hidden="true">
                <button class="ctrl" data-key="left" type="button">←</button>
                <button class="ctrl ctrl-jump" data-key="jump" type="button">↯</button>
                <button class="ctrl" data-key="right" type="button">→</button>
            </div>
        </section>
        <script>
            const labels = __LABELS_JSON__;
            const canvas = document.getElementById("voltGame");
            const ctx = canvas.getContext("2d");
            const levelLabel = document.getElementById("levelLabel");
            const chargeText = document.getElementById("chargeText");
            const chargeFill = document.getElementById("chargeFill");
            const overlay = document.getElementById("overlay");
            const overlayTitle = document.getElementById("overlayTitle");
            const startButton = document.getElementById("startButton");
            const W = canvas.width;
            const H = canvas.height;
            const baseLevels = [
                {
                    spawn: [28, 318],
                    goal: { x: 314, y: 308, w: 22, h: 44 },
                    platforms: [
                        { x: 0, y: 382, w: 360, h: 48 },
                        { x: 112, y: 322, w: 62, h: 12 },
                        { x: 214, y: 282, w: 60, h: 12, fall: true }
                    ],
                    coins: [{ x: 135, y: 292 }, { x: 236, y: 252 }],
                    spikes: [{ x: 198, y: 382, w: 34, h: 22, active: false }],
                    traps: [{ type: "popSpike", triggerX: 164, spike: 0 }]
                },
                {
                    spawn: [26, 318],
                    goal: { x: 306, y: 176, w: 24, h: 44 },
                    platforms: [
                        { x: 0, y: 382, w: 144, h: 48 },
                        { x: 184, y: 382, w: 176, h: 48 },
                        { x: 82, y: 318, w: 72, h: 12 },
                        { x: 184, y: 256, w: 72, h: 12 },
                        { x: 284, y: 216, w: 54, h: 12 }
                    ],
                    coins: [{ x: 110, y: 288 }, { x: 214, y: 226 }, { x: 306, y: 188 }],
                    spikes: [{ x: 148, y: 382, w: 34, h: 22 }, { x: 256, y: 382, w: 28, h: 22, active: false }],
                    traps: [{ type: "popSpike", triggerX: 226, spike: 1 }, { type: "goalShift", triggerX: 272, dx: -34, dy: 0 }]
                },
                {
                    spawn: [28, 318],
                    goal: { x: 310, y: 306, w: 24, h: 44 },
                    reverseZone: { x: 128, y: 0, w: 98, h: 430 },
                    platforms: [
                        { x: 0, y: 382, w: 94, h: 48 },
                        { x: 122, y: 382, w: 92, h: 48 },
                        { x: 246, y: 382, w: 114, h: 48 },
                        { x: 104, y: 306, w: 70, h: 12 },
                        { x: 206, y: 272, w: 58, h: 12, fall: true }
                    ],
                    coins: [{ x: 148, y: 276 }, { x: 226, y: 242 }],
                    spikes: [{ x: 96, y: 382, w: 24, h: 22 }, { x: 218, y: 382, w: 28, h: 22 }],
                    traps: [{ type: "platformDrop", triggerX: 194, platform: 4 }]
                },
                {
                    spawn: [26, 318],
                    goal: { x: 310, y: 104, w: 24, h: 44 },
                    platforms: [
                        { x: 0, y: 382, w: 360, h: 48 },
                        { x: 68, y: 316, w: 58, h: 12, fall: true },
                        { x: 154, y: 258, w: 58, h: 12 },
                        { x: 236, y: 200, w: 58, h: 12 },
                        { x: 298, y: 152, w: 48, h: 12 }
                    ],
                    coins: [{ x: 86, y: 286 }, { x: 174, y: 228 }, { x: 254, y: 170 }],
                    spikes: [{ x: 132, y: 382, w: 30, h: 22 }, { x: 224, y: 382, w: 30, h: 22 }, { x: 276, y: 382, w: 30, h: 22, active: false }],
                    traps: [{ type: "popSpike", triggerX: 250, spike: 2 }, { type: "platformDrop", triggerX: 90, platform: 1 }]
                },
                {
                    spawn: [24, 318],
                    goal: { x: 312, y: 304, w: 24, h: 44 },
                    reverseZone: { x: 204, y: 0, w: 70, h: 430 },
                    platforms: [
                        { x: 0, y: 382, w: 360, h: 48 },
                        { x: 74, y: 318, w: 54, h: 12 },
                        { x: 158, y: 266, w: 58, h: 12, fall: true },
                        { x: 252, y: 318, w: 54, h: 12 }
                    ],
                    coins: [{ x: 94, y: 288 }, { x: 178, y: 236 }, { x: 272, y: 288 }],
                    spikes: [{ x: 132, y: 382, w: 24, h: 22 }, { x: 216, y: 382, w: 24, h: 22 }, { x: 286, y: 382, w: 28, h: 22, active: false }],
                    traps: [{ type: "popSpike", triggerX: 258, spike: 2 }, { type: "goalShift", triggerX: 292, dx: -48, dy: -86 }]
                }
            ];

            let levelIndex = 0;
            let level = null;
            let player = null;
            let particles = [];
            let running = false;
            let deadTimer = 0;
            let finishTimer = 0;
            let charge = 0;
            let deaths = 0;
            let lastTime = 0;
            const keys = { left: false, right: false, jump: false };
            const pressed = { jump: false };

            const clone = (item) => JSON.parse(JSON.stringify(item));
            const rectsHit = (a, b) => (
                a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
            );

            function resetPlayer() {
                player = { x: level.spawn[0], y: level.spawn[1], w: 18, h: 22, vx: 0, vy: 0, grounded: false };
            }

            function loadLevel(index) {
                levelIndex = Math.max(0, Math.min(baseLevels.length - 1, index));
                level = clone(baseLevels[levelIndex]);
                level.platforms.forEach((platform) => {
                    platform.active = true;
                    platform.drop = false;
                    platform.vy = 0;
                });
                level.spikes.forEach((spike) => {
                    if (spike.active !== false) spike.active = true;
                });
                level.traps.forEach((trap) => trap.done = false);
                resetPlayer();
                particles = [];
                deadTimer = 0;
                finishTimer = 0;
                updateHud();
            }

            function updateHud() {
                levelLabel.textContent = `${labels.level} ${String(levelIndex + 1).padStart(2, "0")}`;
                chargeText.textContent = `${labels.charge} ${charge}%`;
                chargeFill.style.width = `${charge}%`;
            }

            function burst(x, y, color) {
                for (let i = 0; i < 12; i += 1) {
                    particles.push({
                        x, y,
                        vx: (Math.random() - 0.5) * 160,
                        vy: (Math.random() - 0.7) * 180,
                        life: 0.6,
                        color
                    });
                }
            }

            function showOverlay(title, buttonText) {
                overlayTitle.textContent = title;
                startButton.textContent = buttonText;
                overlay.classList.add("is-visible");
            }

            function hideOverlay() {
                overlay.classList.remove("is-visible");
            }

            function startGame() {
                charge = 0;
                deaths = 0;
                running = true;
                hideOverlay();
                loadLevel(0);
            }

            function die() {
                if (deadTimer || finishTimer) return;
                deaths += 1;
                deadTimer = 0.72;
                burst(player.x + player.w / 2, player.y + player.h / 2, "#9FE000");
            }

            function completeLevel() {
                if (finishTimer || deadTimer) return;
                finishTimer = 0.58;
                charge = Math.round(((levelIndex + 1) / baseLevels.length) * 100);
                updateHud();
                burst(level.goal.x + 12, level.goal.y + 18, "#C8FF2E");
            }

            function triggerTraps() {
                level.traps.forEach((trap) => {
                    if (trap.done || player.x < trap.triggerX) return;
                    trap.done = true;
                    if (trap.type === "popSpike") {
                        const spike = level.spikes[trap.spike];
                        if (spike) {
                            spike.active = true;
                            burst(spike.x + spike.w / 2, spike.y - 6, "#0E1012");
                        }
                    }
                    if (trap.type === "platformDrop") {
                        const platform = level.platforms[trap.platform];
                        if (platform) platform.drop = true;
                    }
                    if (trap.type === "goalShift") {
                        level.goal.x += trap.dx;
                        level.goal.y += trap.dy;
                        burst(level.goal.x + 12, level.goal.y + 18, "#C8FF2E");
                    }
                });
            }

            function update(dt) {
                particles = particles
                    .map((p) => ({ ...p, x: p.x + p.vx * dt, y: p.y + p.vy * dt, vy: p.vy + 420 * dt, life: p.life - dt }))
                    .filter((p) => p.life > 0);

                if (!running) return;
                if (deadTimer > 0) {
                    deadTimer -= dt;
                    if (deadTimer <= 0) resetPlayer();
                    return;
                }
                if (finishTimer > 0) {
                    finishTimer -= dt;
                    if (finishTimer <= 0) {
                        if (levelIndex === baseLevels.length - 1) {
                            running = false;
                            showOverlay(`${labels.finished} · ${labels.best} ${Math.max(0, 100 - deaths * 3)}`, labels.restart);
                        } else {
                            loadLevel(levelIndex + 1);
                        }
                    }
                    return;
                }

                const reversed = level.reverseZone && player.x + player.w > level.reverseZone.x && player.x < level.reverseZone.x + level.reverseZone.w;
                const left = reversed ? keys.right : keys.left;
                const right = reversed ? keys.left : keys.right;
                const accel = 840;
                const friction = player.grounded ? 0.78 : 0.95;
                if (left) player.vx -= accel * dt;
                if (right) player.vx += accel * dt;
                player.vx *= friction;
                player.vx = Math.max(-176, Math.min(176, player.vx));
                if (keys.jump && !pressed.jump && player.grounded) {
                    player.vy = -318;
                    player.grounded = false;
                    burst(player.x + player.w / 2, player.y + player.h, "#C8FF2E");
                }
                pressed.jump = keys.jump;
                player.vy += 740 * dt;

                const previousY = player.y;
                player.x += player.vx * dt;
                player.x = Math.max(0, Math.min(W - player.w, player.x));
                player.y += player.vy * dt;
                player.grounded = false;

                level.platforms.forEach((platform) => {
                    if (!platform.active) return;
                    if (platform.drop || platform.touched) {
                        platform.vy = Math.min(180, (platform.vy || 0) + 220 * dt);
                        platform.y += platform.vy * dt;
                        if (platform.y > H + 40) platform.active = false;
                    }
                    const wasAbove = previousY + player.h <= platform.y + 4;
                    const isFalling = player.vy >= 0;
                    const overlapsX = player.x + player.w > platform.x && player.x < platform.x + platform.w;
                    if (wasAbove && isFalling && overlapsX && player.y + player.h >= platform.y && player.y + player.h <= platform.y + 18) {
                        player.y = platform.y - player.h;
                        player.vy = 0;
                        player.grounded = true;
                        if (platform.fall) platform.touched = true;
                    }
                });

                triggerTraps();

                level.coins.forEach((coin) => {
                    if (coin.done) return;
                    if (rectsHit(player, { x: coin.x - 8, y: coin.y - 8, w: 16, h: 16 })) {
                        coin.done = true;
                        charge = Math.min(99, charge + 3);
                        updateHud();
                        burst(coin.x, coin.y, "#C8FF2E");
                    }
                });

                level.spikes.forEach((spike) => {
                    if (!spike.active) return;
                    if (rectsHit(player, { x: spike.x + 3, y: spike.y - spike.h, w: spike.w - 6, h: spike.h })) {
                        die();
                    }
                });

                if (player.y > H + 28) die();
                if (rectsHit(player, level.goal)) completeLevel();
            }

            function drawPlatform(platform) {
                if (!platform.active) return;
                ctx.fillStyle = platform.fall || platform.touched ? "rgba(200,255,46,0.78)" : "rgba(255,255,255,0.94)";
                ctx.strokeStyle = "rgba(14,16,18,0.18)";
                ctx.lineWidth = 1;
                roundRect(platform.x, platform.y, platform.w, platform.h, 6);
                ctx.fill();
                ctx.stroke();
            }

            function drawSpike(spike) {
                if (!spike.active) return;
                const count = Math.max(1, Math.floor(spike.w / 12));
                const width = spike.w / count;
                ctx.fillStyle = "#9FE000";
                for (let i = 0; i < count; i += 1) {
                    const x = spike.x + i * width;
                    ctx.beginPath();
                    ctx.moveTo(x, spike.y);
                    ctx.lineTo(x + width / 2, spike.y - spike.h);
                    ctx.lineTo(x + width, spike.y);
                    ctx.closePath();
                    ctx.fill();
                }
            }

            function roundRect(x, y, w, h, r) {
                ctx.beginPath();
                ctx.moveTo(x + r, y);
                ctx.arcTo(x + w, y, x + w, y + h, r);
                ctx.arcTo(x + w, y + h, x, y + h, r);
                ctx.arcTo(x, y + h, x, y, r);
                ctx.arcTo(x, y, x + w, y, r);
                ctx.closePath();
            }

            function draw() {
                ctx.clearRect(0, 0, W, H);
                const gradient = ctx.createLinearGradient(0, 0, W, H);
                gradient.addColorStop(0, "#FFFFFF");
                gradient.addColorStop(0.58, "#F4F5F2");
                gradient.addColorStop(1, "#EEF9D6");
                ctx.fillStyle = gradient;
                ctx.fillRect(0, 0, W, H);

                ctx.globalAlpha = 0.28;
                ctx.strokeStyle = "#0E1012";
                ctx.lineWidth = 1;
                for (let x = -30; x < W; x += 34) {
                    ctx.beginPath();
                    ctx.moveTo(x, 0);
                    ctx.lineTo(x + 78, H);
                    ctx.stroke();
                }
                ctx.globalAlpha = 1;

                if (level.reverseZone) {
                    ctx.fillStyle = "rgba(200,255,46,0.18)";
                    ctx.fillRect(level.reverseZone.x, 0, level.reverseZone.w, H);
                }

                level.platforms.forEach(drawPlatform);
                level.spikes.forEach(drawSpike);

                level.coins.forEach((coin) => {
                    if (coin.done) return;
                    ctx.save();
                    ctx.translate(coin.x, coin.y);
                    ctx.rotate(performance.now() / 420);
                    ctx.fillStyle = "#C8FF2E";
                    roundRect(-7, -7, 14, 14, 5);
                    ctx.fill();
                    ctx.restore();
                });

                ctx.fillStyle = "rgba(14,16,18,0.72)";
                roundRect(level.goal.x, level.goal.y, level.goal.w, level.goal.h, 8);
                ctx.fill();
                ctx.fillStyle = "#C8FF2E";
                ctx.fillRect(level.goal.x + 6, level.goal.y + 9, level.goal.w - 12, level.goal.h - 18);

                particles.forEach((p) => {
                    ctx.globalAlpha = Math.max(0, p.life);
                    ctx.fillStyle = p.color;
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
                    ctx.fill();
                });
                ctx.globalAlpha = 1;

                if (deadTimer > 0) {
                    ctx.globalAlpha = 0.34;
                    ctx.fillStyle = "#9FE000";
                    ctx.fillRect(0, 0, W, H);
                    ctx.globalAlpha = 1;
                } else {
                    ctx.fillStyle = "#0E1012";
                    roundRect(player.x, player.y, player.w, player.h, 7);
                    ctx.fill();
                    ctx.fillStyle = "#C8FF2E";
                    ctx.fillRect(player.x + 5, player.y + 5, player.w - 10, 5);
                }
            }

            function loop(time) {
                const dt = Math.min(0.033, (time - lastTime) / 1000 || 0);
                lastTime = time;
                update(dt);
                draw();
                requestAnimationFrame(loop);
            }

            function setKey(key, value) {
                keys[key] = value;
                if (!value && key === "jump") pressed.jump = false;
            }

            function tapImpulse(key) {
                if (!running || deadTimer > 0 || finishTimer > 0) return;
                if (key === "left") player.vx = Math.max(-176, player.vx - 92);
                if (key === "right") player.vx = Math.min(176, player.vx + 92);
                if (key === "jump" && player.grounded) {
                    player.vy = -318;
                    player.grounded = false;
                    pressed.jump = true;
                    burst(player.x + player.w / 2, player.y + player.h, "#C8FF2E");
                }
            }

            document.addEventListener("keydown", (event) => {
                if (event.key === "ArrowLeft" || event.key === "a" || event.key === "A") {
                    setKey("left", true);
                    tapImpulse("left");
                }
                if (event.key === "ArrowRight" || event.key === "d" || event.key === "D") {
                    setKey("right", true);
                    tapImpulse("right");
                }
                if (event.key === "ArrowUp" || event.key === " " || event.key === "w" || event.key === "W") {
                    setKey("jump", true);
                    tapImpulse("jump");
                }
            });
            document.addEventListener("keyup", (event) => {
                if (event.key === "ArrowLeft" || event.key === "a" || event.key === "A") setKey("left", false);
                if (event.key === "ArrowRight" || event.key === "d" || event.key === "D") setKey("right", false);
                if (event.key === "ArrowUp" || event.key === " " || event.key === "w" || event.key === "W") setKey("jump", false);
            });
            document.querySelectorAll(".ctrl").forEach((button) => {
                const key = button.dataset.key;
                button.addEventListener("pointerdown", (event) => {
                    event.preventDefault();
                    button.setPointerCapture(event.pointerId);
                    setKey(key, true);
                    tapImpulse(key);
                    canvas.focus();
                });
                button.addEventListener("pointerup", () => setKey(key, false));
                button.addEventListener("pointercancel", () => setKey(key, false));
                button.addEventListener("pointerleave", () => setKey(key, false));
            });
            startButton.addEventListener("click", () => {
                if (running) {
                    loadLevel(levelIndex);
                    hideOverlay();
                    return;
                }
                startGame();
            });

            loadLevel(0);
            showOverlay(labels.ready, labels.start);
            requestAnimationFrame(loop);
        </script>
        <style>
            * { box-sizing: border-box; }
            html, body {
                background: transparent;
                margin: 0;
                overflow: hidden;
                touch-action: manipulation;
            }
            body {
                color: #0E1012;
                font-family: "SF Pro Text", -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
            }
            .sb-lounge-game {
                background:
                    radial-gradient(circle at 22% 6%, rgba(200, 255, 46, 0.24), transparent 34%),
                    linear-gradient(150deg, rgba(255, 255, 255, 0.98), rgba(244, 245, 242, 0.94));
                border: 1px solid rgba(14, 16, 18, 0.12);
                border-radius: 26px;
                box-shadow: 0 22px 54px rgba(14, 16, 18, 0.13);
                height: 540px;
                margin: 0 auto;
                max-width: 520px;
                overflow: hidden;
                padding: 14px;
                width: 100%;
            }
            .sb-lounge-head {
                align-items: center;
                display: flex;
                gap: 12px;
                justify-content: space-between;
                margin-bottom: 12px;
            }
            .sb-lounge-head span,
            .sb-lounge-meter small {
                color: rgba(14, 16, 18, 0.66);
                display: block;
                font-size: 10px;
                font-weight: 820;
                text-transform: uppercase;
            }
            .sb-lounge-head strong {
                color: #0E1012;
                display: block;
                font-size: 24px;
                font-weight: 900;
                line-height: 1.05;
                margin-top: 2px;
            }
            .sb-lounge-meter {
                min-width: 142px;
            }
            .sb-lounge-meter i {
                background: rgba(14, 16, 18, 0.14);
                border-radius: 999px;
                display: block;
                height: 10px;
                margin-top: 7px;
                overflow: hidden;
            }
            .sb-lounge-meter b {
                background: linear-gradient(90deg, #C8FF2E, #9FE000);
                border-radius: inherit;
                display: block;
                height: 100%;
                transition: width 220ms ease;
                width: 0%;
            }
            .sb-game-stage {
                background: rgba(255, 255, 255, 0.84);
                border: 1px solid rgba(14, 16, 18, 0.10);
                border-radius: 22px;
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.76);
                overflow: hidden;
                position: relative;
            }
            canvas {
                display: block;
                height: 338px;
                outline: 0;
                width: 100%;
            }
            @media (min-width: 431px) {
                .sb-lounge-game {
                    height: 456px;
                }
                canvas {
                    height: 250px;
                }
                .ctrl {
                    min-height: 52px;
                }
            }
            .sb-game-overlay {
                align-items: center;
                backdrop-filter: blur(14px);
                background: rgba(255, 255, 255, 0.78);
                display: none;
                flex-direction: column;
                gap: 14px;
                inset: 0;
                justify-content: center;
                position: absolute;
            }
            .sb-game-overlay.is-visible {
                display: flex;
            }
            .sb-game-overlay strong {
                color: #0E1012;
                font-size: 28px;
                font-weight: 920;
            }
            .sb-game-overlay button,
            .ctrl {
                appearance: none;
                border: 0;
                cursor: pointer;
                font-family: inherit;
            }
            .sb-game-overlay button {
                background: #C8FF2E;
                border: 1px solid rgba(159, 224, 0, 0.42);
                border-radius: 18px;
                box-shadow: 0 16px 34px rgba(200, 255, 46, 0.24), 0 10px 22px rgba(14, 16, 18, 0.08);
                color: #0E1012;
                font-size: 15px;
                font-weight: 900;
                min-width: 148px;
                padding: 13px 18px;
            }
            .sb-lounge-controls {
                display: grid;
                gap: 10px;
                grid-template-columns: 1fr 1.18fr 1fr;
                margin-top: 12px;
            }
            .ctrl {
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(14, 16, 18, 0.12);
                border-radius: 18px;
                box-shadow: 0 12px 26px rgba(14, 16, 18, 0.08);
                color: #0E1012;
                font-size: 24px;
                font-weight: 900;
                min-height: 62px;
            }
            .ctrl:active {
                background: #C8FF2E;
                transform: translateY(1px);
            }
            .ctrl-jump {
                background: #C8FF2E;
                border-color: rgba(159, 224, 0, 0.42);
                box-shadow: 0 16px 34px rgba(200, 255, 46, 0.26), 0 12px 26px rgba(14, 16, 18, 0.08);
                color: #0E1012;
                font-size: 28px;
            }
            @media (max-width: 430px) {
                .sb-lounge-game {
                    border-radius: 22px;
                    height: 528px;
                    padding: 11px;
                }
                .sb-lounge-head strong {
                    font-size: 21px;
                }
                .sb-lounge-meter {
                    min-width: 128px;
                }
                .ctrl {
                    min-height: 56px;
                }
                canvas {
                    height: 330px;
                }
            }
        </style>
    """
    game_html = (
        game_html
        .replace("__LABELS_JSON__", labels_json)
        .replace("__LOUNGE_ARIA__", guvenli_metin(t("lounge.aria"), 80))
        .replace("__GAME_TITLE__", guvenli_metin(labels["gameTitle"], 80))
        .replace("__LEVEL_LABEL__", guvenli_metin(labels["level"], 30))
        .replace("__CHARGE_LABEL__", guvenli_metin(labels["charge"], 30))
        .replace("__READY_LABEL__", guvenli_metin(labels["ready"], 80))
        .replace("__START_LABEL__", guvenli_metin(labels["start"], 40))
    )

    st.markdown(
        f"""
        <section class="sb-lounge-shell">
            <div class="sb-kicker">{t("lounge.kicker")}</div>
            <h1>{t("lounge.title")}</h1>
            <p>{t("lounge.subtitle")}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    sayfa_ustune_hizala(f"lounge_scroll_{st.session_state.get('bekleme_salonu_scroll_nonce', 0)}")
    st.markdown('<div class="sb-lounge-game-anchor" aria-hidden="true"></div>', unsafe_allow_html=True)
    components.html(game_html, height=540, scrolling=False)
