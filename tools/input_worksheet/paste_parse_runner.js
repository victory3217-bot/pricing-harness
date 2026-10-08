// Runs the calculator's parseSheetPaste (the code between the <paste-parser> markers in
// docs/calculator/index.html) on text read from stdin and prints the result as JSON.
// Used by qa_check_input_worksheet.py; no DOM is needed because the parser is a pure function.
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "..", "..", "docs", "calculator", "index.html"), "utf8");
const start = html.indexOf("// <paste-parser>");
const end = html.indexOf("// </paste-parser>");
if (start < 0 || end < 0) {
  console.error("paste-parser markers not found in docs/calculator/index.html");
  process.exit(2);
}
const parseSheetPaste = new Function(html.slice(start, end) + "\nreturn parseSheetPaste;")();
const input = fs.readFileSync(0, "utf8");
process.stdout.write(JSON.stringify(parseSheetPaste(input)));
