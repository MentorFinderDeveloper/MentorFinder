const fs = require("fs");
const path = require("path");

// Strip terminal color codes before serializing Jest output into XML.
const ANSI_ESCAPE_RE = /\u001b\[[0-9;]*m/g;
// Remove characters that are invalid in XML 1.0 documents.
const ILLEGAL_XML_RE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u0084\u0086-\u009f]/g;

const escapeXml = (value) => String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");

const sanitizeText = (value) => String(value)
    .replace(ANSI_ESCAPE_RE, "")
    .replace(ILLEGAL_XML_RE, "");

const shortenMessage = (value) => sanitizeText(value).split("\n")[0];

module.exports = (results) => {
    // SonarQube expects a <testExecutions> document rather than raw Jest JSON.
    const lines = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", "<testExecutions version=\"1\">"];

    for (const suite of results.testResults || []) {
        lines.push(`  <file path="${escapeXml(sanitizeText(suite.testFilePath || ""))}">`);

        for (const testCase of suite.testResults || []) {
            const testName = sanitizeText(testCase.fullName || testCase.title || "");
            const duration = Number(testCase.duration) || 0;

            lines.push(`    <testCase name="${escapeXml(testName)}" duration="${duration}">`);

            if (testCase.status === "failed") {
                for (const rawMessage of testCase.failureMessages || []) {
                    const failureMessage = sanitizeText(rawMessage);
                    lines.push(`      <failure message="${escapeXml(shortenMessage(rawMessage))}"><![CDATA[${failureMessage}]]></failure>`);
                }
            }

            lines.push("    </testCase>");
        }

        lines.push("  </file>");
    }

    lines.push("</testExecutions>");

    // Emit the report at the project root because sonar-project.properties reads it from there.
    fs.writeFileSync(path.join(process.cwd(), "test-report.xml"), `${lines.join("\n")}\n`, "utf8");
    return results;
};
