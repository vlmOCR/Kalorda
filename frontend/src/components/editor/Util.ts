// 获取dom节点的innerText 并对{和}符号进行转义
export function getInnerText(domNode: any) {
    if (!domNode) {
        return '';
    }
    // Prefer textContent to avoid whitespace normalization that can convert full-width spaces.
    const rawText = (domNode.textContent ?? domNode.innerText ?? '') as string;
    if (rawText.length === 0) {
        return '';
    }
    const innerText = rawText.replace(/[{}]/g, (match: any) => `\\${match}`);
    return innerText;
}

export function isNotEmpty(value: any) {
    return value !== null && value !== undefined && value !== '';
}

export const $dom = (selector: string) => {
    return document.querySelector(selector) as HTMLElement;
};
