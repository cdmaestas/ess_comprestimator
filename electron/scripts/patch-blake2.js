const fs = require('fs');
const path = require('path');

const target = path.join(__dirname, '../node_modules/app-builder-lib/out/targets/blockmap/blockmap.js');

if (!fs.existsSync(target)) {
  process.exit(0);
}

const original = fs.readFileSync(target, 'utf8');
const patched = original.replace(/@noble\/hashes\/blake2\.js/g, '@noble/hashes/blake2');

if (original !== patched) {
  fs.writeFileSync(target, patched);
  console.log('patched app-builder-lib/blockmap.js: blake2.js → blake2');
}
