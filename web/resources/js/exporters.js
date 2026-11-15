import { saveBlob } from './api';

/**
 * Self-contained copy of an on-screen SVG: computed text styles are inlined and a
 * background is added, so the file looks the same outside the page.
 */
function standaloneSvg(svg) {
    const clone = svg.cloneNode(true);
    const source = svg.querySelectorAll('*');
    const target = clone.querySelectorAll('*');
    source.forEach((node, i) => {
        if (node.tagName === 'text' || node.tagName === 'tspan') {
            const cs = getComputedStyle(node);
            target[i].setAttribute('fill', node.getAttribute('fill') && node.getAttribute('fill') !== 'currentColor' ? node.getAttribute('fill') : cs.fill);
            target[i].setAttribute('font-family', cs.fontFamily);
            target[i].setAttribute('font-size', cs.fontSize);
            target[i].setAttribute('font-weight', cs.fontWeight);
        } else if (node.getAttribute?.('stroke') === 'currentColor' || node.getAttribute?.('fill') === 'currentColor') {
            const cs = getComputedStyle(node);
            if (node.getAttribute('stroke') === 'currentColor') target[i].setAttribute('stroke', cs.stroke);
            if (node.getAttribute('fill') === 'currentColor') target[i].setAttribute('fill', cs.fill);
        }
        target[i].removeAttribute('tabindex');
    });

    const vb = svg.viewBox.baseVal;
    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bg.setAttribute('x', vb.x);
    bg.setAttribute('y', vb.y);
    bg.setAttribute('width', vb.width);
    bg.setAttribute('height', vb.height);
    bg.setAttribute('fill', getComputedStyle(document.body).backgroundColor);
    clone.insertBefore(bg, clone.firstChild);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', vb.width);
    clone.setAttribute('height', vb.height);

    return new XMLSerializer().serializeToString(clone);
}

export function downloadSvg(svg, filename) {
    saveBlob(new Blob([standaloneSvg(svg)], { type: 'image/svg+xml' }), `${filename}.svg`);
}

export async function downloadPng(svg, filename, scale = 2) {
    const markup = standaloneSvg(svg);
    const vb = svg.viewBox.baseVal;
    const img = new Image();
    const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml' }));
    await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = reject;
        img.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = vb.width * scale;
    canvas.height = vb.height * scale;
    const ctx = canvas.getContext('2d');
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    canvas.toBlob((blob) => saveBlob(blob, `${filename}.png`), 'image/png');
}

export function downloadCsv(rows, filename) {
    const esc = (v) => {
        const s = v === null || v === undefined ? '' : String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const text = rows.map((r) => r.map(esc).join(',')).join('\n') + '\n';
    saveBlob(new Blob([text], { type: 'text/csv;charset=utf-8' }), `${filename}.csv`);
}
