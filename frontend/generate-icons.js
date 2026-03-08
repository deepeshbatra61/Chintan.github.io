/**
 * Generates Chintan app icons for Android at all required densities.
 *
 * Design:
 *   - Dark navy/black background (#0a0a1a)
 *   - Bold white "C" centred using pixel-drawn strokes
 *   - Red accent dot (#DC2626) on the open end of the C
 *   - Square variant: ic_launcher.png
 *   - Round variant: ic_launcher_round.png (circular mask)
 */

const { Jimp } = require("jimp");
const path = require("path");
const fs = require("fs");

const RES_BASE =
  "C:/Users/Deepesh Batra/Chintan.github.io/frontend/android/app/src/main/res";

const SIZES = [
  { folder: "mipmap-mdpi",    size: 48  },
  { folder: "mipmap-hdpi",    size: 72  },
  { folder: "mipmap-xhdpi",   size: 96  },
  { folder: "mipmap-xxhdpi",  size: 144 },
  { folder: "mipmap-xxxhdpi", size: 192 },
];

// Colours as 32-bit RGBA ints (Jimp uses 0xRRGGBBAA)
const BG    = 0x0a0a1aff; // dark navy
const WHITE = 0xffffffff;
const RED   = 0xdc2626ff;

/**
 * Draw a filled circle of `radius` pixels centred at (cx, cy).
 */
function fillCircle(img, cx, cy, radius, colour) {
  const r2 = radius * radius;
  for (let dy = -radius; dy <= radius; dy++) {
    for (let dx = -radius; dx <= radius; dx++) {
      if (dx * dx + dy * dy <= r2) {
        const px = Math.round(cx + dx);
        const py = Math.round(cy + dy);
        if (px >= 0 && py >= 0 && px < img.bitmap.width && py < img.bitmap.height) {
          img.setPixelColor(colour, px, py);
        }
      }
    }
  }
}

/**
 * Draw a thick arc from startAngle to endAngle (degrees, 0 = right, CCW).
 * Renders as a sequence of filled circles along the arc path.
 */
function drawArc(img, cx, cy, radius, thickness, startDeg, endDeg, colour) {
  const steps = Math.ceil((Math.abs(endDeg - startDeg) / 360) * 2 * Math.PI * radius * 2);
  const halfT = thickness / 2;
  for (let i = 0; i <= steps; i++) {
    const angle = (startDeg + (endDeg - startDeg) * (i / steps)) * (Math.PI / 180);
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    fillCircle(img, Math.round(x), Math.round(y), Math.ceil(halfT), colour);
  }
}

/**
 * Apply a circular mask so pixels outside the circle become transparent.
 */
function applyCircleMask(img) {
  const { width, height } = img.bitmap;
  const cx = width / 2;
  const cy = height / 2;
  const r  = Math.min(cx, cy);
  img.scan(0, 0, width, height, function (x, y, idx) {
    const dx = x - cx;
    const dy = y - cy;
    if (dx * dx + dy * dy > r * r) {
      // Set alpha to 0
      this.bitmap.data[idx + 3] = 0;
    }
  });
}

async function generateIcon(size) {
  const img = new Jimp({ width: size, height: size, color: BG });
  const { width, height } = img.bitmap;

  const cx = width  / 2;
  const cy = height / 2;

  // ── "C" arc parameters ────────────────────────────────────────────────
  // The C spans from ~45° to ~315° (leaving a gap on the right = open side).
  // We use two concentric arcs (outer + inner) to form a thick stroke.
  const arcRadius    = size * 0.30;          // centre of the stroke
  const strokeWidth  = size * 0.13;
  const gapDeg       = 60;                   // total gap angle on the right
  const startDeg     = gapDeg / 2;           // ~30°  (bottom-right opening)
  const endDeg       = 360 - gapDeg / 2;    // ~330° (top-right opening)

  drawArc(img, cx, cy, arcRadius, strokeWidth, startDeg, endDeg, WHITE);

  // ── Red accent dot on the open end of the C ──────────────────────────
  // Place it at the midpoint of the gap (0°, i.e. the right side).
  const dotAngle  = 0 * (Math.PI / 180);
  const dotRadius = size * 0.10;
  const dotX = cx + arcRadius * Math.cos(dotAngle);
  const dotY = cy + arcRadius * Math.sin(dotAngle);
  fillCircle(img, Math.round(dotX), Math.round(dotY), Math.round(dotRadius), RED);

  return img;
}

async function main() {
  for (const { folder, size } of SIZES) {
    const dir = path.join(RES_BASE, folder);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    const base = await generateIcon(size);

    // Square launcher icon
    await base.clone().write(path.join(dir, "ic_launcher.png"));

    // Round launcher icon — apply circular mask
    const round = base.clone();
    applyCircleMask(round);
    await round.write(path.join(dir, "ic_launcher_round.png"));

    // Foreground layer (same design, used by adaptive icon on API 26+)
    await base.clone().write(path.join(dir, "ic_launcher_foreground.png"));

    console.log(`✓ ${folder} (${size}×${size})`);
  }

  console.log("\nAll icons generated.");
}

main().catch((err) => { console.error(err); process.exit(1); });
