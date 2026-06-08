const path = require("path");

const helper = function () {
  return path.sep.length > 0;
};

function runLegacyFlow() {
  return helper();
}

module.exports = { helper, runLegacyFlow };
