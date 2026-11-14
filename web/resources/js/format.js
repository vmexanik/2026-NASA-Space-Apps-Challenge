import { i18n } from './i18n';

const loc = () => (i18n.global.locale.value === 'uk' ? 'uk-UA' : 'en-GB');

export function monthName(month, style = 'short') {
    return new Intl.DateTimeFormat(loc(), { month: style }).format(new Date(2001, month - 1, 1));
}

export function monthYear(year, month) {
    return new Intl.DateTimeFormat(loc(), { month: 'long', year: 'numeric' }).format(new Date(year, month - 1, 1));
}

export function num(value, digits = 0) {
    if (value === null || value === undefined) return '—';
    return new Intl.NumberFormat(loc(), { maximumFractionDigits: digits }).format(value);
}

/** 1234 → 1.2k (for small heatmap cells). */
export function compact(value) {
    if (value === null || value === undefined) return '';
    return new Intl.NumberFormat(loc(), { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

export function pct(value) {
    if (value === null || value === undefined) return '—';
    const sign = value > 0 ? '+' : '';
    return `${sign}${num(value, 0)} %`;
}

export function date(iso) {
    return new Intl.DateTimeFormat(loc(), { dateStyle: 'medium' }).format(new Date(iso));
}
