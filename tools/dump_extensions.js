// Dump the real block definitions of every built-in Scratch extension from scratch-vm.
// usage: node tools/dump_extensions.js OUT.json   (run where `npm install scratch-vm scratch-storage` was done)
process.on('unhandledRejection', () => {});
const fs = require('fs');
const VirtualMachine = require('scratch-vm');
const {ScratchStorage} = require('scratch-storage');
console.warn = () => {}; console.log = () => {};
const IDS = ['pen', 'music', 'videoSensing', 'text2speech', 'translate', 'makeymakey', 'microbit', 'ev3', 'boost', 'wedo2', 'gdxfor'];
(async () => {
  const vm = new VirtualMachine();
  vm.attachStorage(new ScratchStorage());
  const out = {};
  for (const id of IDS) {
    try { await vm.extensionManager.loadExtensionURL(id); } catch (e) { out[id] = {error: String(e)}; }
  }
  for (const info of vm.runtime._blockInfo) {
    const menus = {};
    for (const [name, m] of Object.entries(info.menuInfo || {})) {
      const items = Array.isArray(m.items) ? m.items.map(i => (i && typeof i === 'object') ? String(i.value) : String(i)) : 'dynamic';
      menus[name] = {acceptReporters: !!m.acceptReporters, items, opcode: `${info.id}_menu_${name}`};
    }
    const blocks = [];
    for (const b of info.blocks) {
      if (!b.info || !b.info.opcode) continue; // separators / labels
      const args = {};
      for (const [n, a] of Object.entries(b.info.arguments || {})) {
        args[n] = {type: a.type, menu: a.menu || null, default: a.defaultValue === undefined ? null : a.defaultValue};
      }
      blocks.push({opcode: `${info.id}_${b.info.opcode}`, blockType: b.info.blockType, text: String(b.info.text), arguments: args,
                   isTerminal: !!b.info.isTerminal, branchCount: b.info.branchCount || 0});
    }
    out[info.id] = {name: info.name, color1: info.color1, blocks, menus};
  }
  fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 1));
  process.stderr.write('dumped ' + Object.keys(out).join(',') + '\n');
  process.exit(0);
})();
