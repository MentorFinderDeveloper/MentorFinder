import katex from "katex";

interface LatexTextProps {
    text: string;
    forceInlineMath?: boolean;
}

interface LatexSegment {
    kind: "text" | "math";
    value: string;
    displayMode?: boolean;
}

interface Delimiter {
    open: string;
    close: string;
    displayMode: boolean;
}

// Support both TeX-style $...$ syntax and escaped bracket delimiters from backend content.
const DELIMITERS: Delimiter[] = [
    { open: "$$", close: "$$", displayMode: true },
    { open: "\\[", close: "\\]", displayMode: true },
    { open: "\\(", close: "\\)", displayMode: false },
    { open: "$", close: "$", displayMode: false },
];

// Merge adjacent plain-text fragments so React renders fewer wrapper nodes.
const pushTextSegment = (segments: LatexSegment[], value: string) => {
    if (value === "") {
        return;
    }

    const previousSegment = segments[segments.length - 1];
    if (previousSegment?.kind === "text") {
        previousSegment.value += value;
        return;
    }

    segments.push({ kind: "text", value });
};

// Split mixed content into text and math segments while preserving unmatched delimiters as text.
const parseLatexSegments = (text: string): LatexSegment[] => {
    const segments: LatexSegment[] = [];
    let cursor = 0;

    while (cursor < text.length) {
        let matchedDelimiter: Delimiter | undefined;

        for (const delimiter of DELIMITERS) {
            if (text.startsWith(delimiter.open, cursor)) {
                matchedDelimiter = delimiter;
                break;
            }
        }

        if (matchedDelimiter === undefined) {
            pushTextSegment(segments, text[cursor]);
            cursor += 1;
            continue;
        }

        const contentStart = cursor + matchedDelimiter.open.length;
        const contentEnd = text.indexOf(matchedDelimiter.close, contentStart);

        if (contentEnd === -1) {
            pushTextSegment(segments, matchedDelimiter.open);
            cursor += matchedDelimiter.open.length;
            continue;
        }

        const formula = text.slice(contentStart, contentEnd);
        if (formula === "") {
            pushTextSegment(segments, matchedDelimiter.open + matchedDelimiter.close);
            cursor = contentEnd + matchedDelimiter.close.length;
            continue;
        }

        segments.push({
            kind: "math",
            value: formula,
            displayMode: matchedDelimiter.displayMode,
        });
        cursor = contentEnd + matchedDelimiter.close.length;
    }

    return segments;
};

// KaTeX returns HTML, so rendering goes through dangerouslySetInnerHTML for both display modes.
const renderMathSegment = (value: string, displayMode: boolean, key: string) => {
    const html = katex.renderToString(value, {
        displayMode,
        throwOnError: false,
        strict: "ignore",
        trust: false,
    });

    if (displayMode) {
        return (
            <div
                key={key}
                className="latexTextDisplay"
                dangerouslySetInnerHTML={{ __html: html }}
            />
        );
    }

    return (
        <span
            key={key}
            className="latexTextInline"
            dangerouslySetInnerHTML={{ __html: html }}
        />
    );
};

// Preserve original newlines from abstracts and titles without wrapping the whole block in <pre>.
const renderTextWithLineBreaks = (value: string) => {
    const lines = value.split("\n");

    return lines.map((line, lineIndex) => (
        <span key={`line-${lineIndex}`}>
            {line}
            {lineIndex < lines.length - 1 && <br />}
        </span>
    ));
};

const LatexText = ({ text, forceInlineMath = false }: LatexTextProps) => {
    // Parsing once here keeps the JSX below focused on rendering concerns.
    const segments = parseLatexSegments(text);

    return (
        <>
            {segments.map((segment, index) => (
                segment.kind === "math"
                    ? renderMathSegment(
                        segment.value,
                        forceInlineMath ? false : Boolean(segment.displayMode),
                        `math-${index}`,
                    )
                    : (
                        <span key={`text-${index}`}>
                            {renderTextWithLineBreaks(segment.value)}
                        </span>
                    )
            ))}
        </>
    );
};

export default LatexText;
