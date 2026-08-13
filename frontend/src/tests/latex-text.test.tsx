import { render, screen } from "@testing-library/react";
import LatexText from "../components/LatexText";


describe("LatexText", () => {
    it("renders plain text through React escaping", () => {
        const { container } = render(<LatexText text={'<img src=x onerror="alert(1)">'} />);

        expect(screen.getByText(/<img src=x/)).toBeInTheDocument();
        expect(container.querySelector("img")).toBeNull();
    });

    it("does not trust KaTeX HTML-like commands", () => {
        const { container } = render(<LatexText text={"$\\htmlId{xss-target}{x}$"} />);

        expect(container.querySelector("#xss-target")).toBeNull();
    });
});
