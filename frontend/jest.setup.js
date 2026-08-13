// Jest.setup.js
import "@testing-library/jest-dom";

// Mock IntersectionObserver so scroll-driven components can be tested in jsdom.
class MockIntersectionObserver {
    constructor(callback) {
        this.callback = callback;
        this.elements = new Set();
        MockIntersectionObserver.instances.push(this);
    }

    observe = (element) => {
        this.elements.add(element);
    };

    unobserve = (element) => {
        this.elements.delete(element);
    };

    disconnect = () => {
        this.elements.clear();
    };

    trigger = (element, isIntersecting = true) => {
        this.callback([
            {
                isIntersecting,
                target: element,
                intersectionRatio: isIntersecting ? 1 : 0,
            },
        ], this);
    };

    static instances = [];

    static reset() {
        MockIntersectionObserver.instances = [];
    }
}

Object.defineProperty(window, "IntersectionObserver", {
    writable: true,
    configurable: true,
    value: MockIntersectionObserver,
});

Object.defineProperty(global, "IntersectionObserver", {
    writable: true,
    configurable: true,
    value: MockIntersectionObserver,
});

global.__mockIntersectionObserver = MockIntersectionObserver;

// jsdom does not implement these browser scrolling APIs, so tests stub them with no-ops.
if (typeof window.scrollBy !== "function") {
    window.scrollBy = () => {};
}

if (typeof window.scrollTo !== "function") {
    window.scrollTo = () => {};
}

if (typeof Element !== "undefined" && typeof Element.prototype.scrollIntoView !== "function") {
    Element.prototype.scrollIntoView = () => {};
}
