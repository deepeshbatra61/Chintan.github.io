/**
 * Resizes the official Chintan logo to all required Android icon sizes.
 */

const { Jimp } = require("jimp");
const path = require("path");
const fs = require("fs");

const LOGO_SRC = "C:/Users/Deepesh Batra/Downloads/chintan-logo-hd-red_2.png";
const RES_BASE = "C:/Users/Deepesh Batra/Chintan.github.io/frontend/android/app/src/main/res";
const PUBLIC_DIR = "C:/Users/Deepesh Batra/Chintan.github.io/frontend/public";

const SIZES = [
  { folder: "mipmap-mdpi",    size: 48  },
  { folder: "mipmap-hdpi",    size: 72  },
  { folder: "mipmap-xhdpi",   size: 96  },
  { folder: "mipmap-xxhdpi",  size: 144 },
  { folder: "mipmap-xxxhdpi", size: 192 },
];

async function main() {
  const src = await Jimp.read(LOGO_SRC);

  for (const { folder, size } of SIZES) {
    const dir = path.join(RES_BASE, folder);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    const resized = src.clone().resize({ w: size, h: size });
    await resized.write(path.join(dir, "ic_launcher.png"));
    await resized.clone().write(path.join(dir, "ic_launcher_round.png"));
    await resized.clone().write(path.join(dir, "ic_launcher_foreground.png"));
    console.log(`✓ ${folder} (${size}×${size})`);
  }

  // Web app favicons
  await src.clone().resize({ w: 192, h: 192 }).write(path.join(PUBLIC_DIR, "logo192.png"));
  await src.clone().resize({ w: 512, h: 512 }).write(path.join(PUBLIC_DIR, "logo512.png"));
  console.log("✓ public/logo192.png and public/logo512.png");

  console.log("\nAll icons generated.");
}

main().catch((err) => { console.error(err); process.exit(1); });
