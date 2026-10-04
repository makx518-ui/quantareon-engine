const path = require('node:path');
// Register before opening Copilot in an isolated server-owned browser context.
module.exports = async function registerTelepat(context) {
  await context.addInitScript({path:path.join(__dirname, 'autoload.js')});
};
