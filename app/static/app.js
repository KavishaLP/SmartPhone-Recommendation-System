/* Simplified recommender UI — reads the local DB only. No scrape controls. */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const num = (value, digits = 0) =>
  value == null || Number.isNaN(value)
    ? '—'
    : Number(value).toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

const score2 = (value) => (value == null ? '—' : Number(value).toFixed(2));

const money = (value, currency) => {
  if (value == null) return '—';
  const symbols = { USD: '$', EUR: '€', GBP: '£', INR: '₹', LKR: 'Rs ' };
  return `${symbols[currency] || ''}${num(value, 0)}${symbols[currency] ? '' : ' ' + (currency || '')}`.trim();
};

function scoreColor(value) {
  if (value == null) return null;
  const clamped = Math.max(0, Math.min(1, value));
  return `hsl(${clamped * 132} 68% ${38 + clamped * 11}%)`;
}

function phoneLabel(phone) {
  return phone.canonical_name || phone.name || phone.raw_title || 'Unknown phone';
}

function phoneImageSrc(phone) {
  const id = phone.id ?? phone.smartphone_id;
  if (id) return `/phones/${id}/image`;
  return phone.image_url || '';
}

function phoneImageFailed(img) {
  const wrap = img.closest('.phone-image-wrap');
  if (!wrap || wrap.classList.contains('broken')) return;
  wrap.classList.add('broken');
  img.remove();
  const initial = (wrap.dataset.initial || '?').charAt(0).toUpperCase();
  wrap.innerHTML = `<span>${esc(initial)}</span>`;
}

function phoneImageMarkup(phone, sizeClass = '') {
  const label = esc(phoneLabel(phone));
  const initial = esc((phone.brand || phoneLabel(phone)).charAt(0).toUpperCase());
  const src = phoneImageSrc(phone);
  if (src) {
    return `<div class="phone-image-wrap ${sizeClass}" data-initial="${initial}">
      <img src="${esc(src)}" alt="${label}" loading="lazy"
        onerror="phoneImageFailed(this)">
    </div>`;
  }
  return `<div class="phone-image-wrap ${sizeClass} placeholder"><span>${initial}</span></div>`;
}

function starRatingMarkup(rating, count) {
  if (rating == null) return '';
  const clamped = Math.max(0, Math.min(5, Number(rating)));
  const full = Math.floor(clamped);
  const partial = clamped - full >= 0.5;
  let stars = '★'.repeat(full);
  if (partial) stars += '½';
  stars = stars.padEnd(partial ? 4 : 5, '☆');
  const countText = count != null ? ` (${num(count)})` : '';
  return `<span class="stars" title="${clamped.toFixed(1)} out of 5">${stars}</span><span class="dim small">${countText}</span>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* empty */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function toast(title, message = '', kind = '') {
  const node = document.createElement('div');
  node.className = `toast ${kind}`;
  node.innerHTML = `<div class="toast-title">${esc(title)}</div>${
    message ? `<div class="toast-msg">${esc(message)}</div>` : ''
  }`;
  $('#toasts').appendChild(node);
  setTimeout(() => {
    node.style.opacity = '0';
    node.style.transition = 'all .3s';
    setTimeout(() => node.remove(), 320);
  }, 4200);
}

function emptyState(title, message) {
  return `<div class="empty">
    <div class="empty-title">${esc(title)}</div>
    <div class="empty-msg">${message}</div>
  </div>`;
}

const skeletons = (count = 3) =>
  `<div class="grid" style="gap:12px">${'<div class="skeleton"></div>'.repeat(count)}</div>`;

const THEME_KEY = 'phone-recommender-theme';

/** Lucide icons — moon = enable dark mode, sun = enable light mode */
const ICON_MOON =
  '<svg class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';
const ICON_SUN =
  '<svg class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>';

function isDarkTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark';
}

function updateThemeButton() {
  const btn = $('#btn-theme');
  if (!btn) return;
  const dark = isDarkTheme();
  btn.innerHTML = dark ? ICON_SUN : ICON_MOON;
  const label = dark ? 'Switch to light mode' : 'Switch to dark mode';
  btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
  btn.setAttribute('aria-label', label);
  btn.title = label;
}

function toggleTheme() {
  const next = isDarkTheme() ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem(THEME_KEY, next);
  updateThemeButton();
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'dark' || saved === 'light') {
    document.documentElement.setAttribute('data-theme', saved);
  }
  updateThemeButton();
}

const state = {
  aspects: [],
  health: null,
  features: [],
  weights: {},
};

const VIEW_META = {
  recommend: ['Recommend', 'Set aspect priorities; ranks phones from Amazon review ABSA scores'],
  phones: ['Phones', 'Browse smartphones with aspect scores from Amazon reviews'],
};

const PRESETS = {
  Balanced: {},
  Photography: { camera: 10, display: 6, performance: 4, battery: 4 },
  'Battery life': { battery: 10, performance: 4, price: 4 },
  Gaming: { performance: 10, display: 8, battery: 6 },
  'Best value': { affordability: 8, price: 8, battery: 5, performance: 5 },
};

function setBadges(stats) {
  $('#badge-phones').textContent = num(stats.phones);
}

async function loadHealth() {
  try {
    const health = await api('/health');
    state.health = health;
    $('#health-dot').className = 'dot ok';
    $('#health-text').textContent = `v${health.version} · DB ready`;
    $('#engine-chip').textContent = `engine: ${health.absa_engine}`;
  } catch {
    $('#health-dot').className = 'dot off';
    $('#health-text').textContent = 'API unreachable';
  }
}

async function loadBadges() {
  try {
    setBadges(await api('/stats'));
  } catch { /* ignore */ }
}

function renderWeightControls() {
  const keys = [...state.aspects.map((a) => a.aspect), 'affordability'];

  $('#presets').innerHTML = Object.keys(PRESETS)
    .map((name) => `<div class="preset" data-preset="${esc(name)}">${esc(name)}</div>`)
    .join('');

  $('#weights').innerHTML = keys
    .map((key) => {
      const label = key === 'affordability' ? 'Affordability (price)' : key;
      state.weights[key] = state.weights[key] ?? 5;
      return `<div class="weight">
        <div class="weight-head">
          <span class="weight-name">${esc(label)}</span>
          <span class="weight-raw" id="raw-${key}">${state.weights[key]}</span>
          <span class="weight-pct" id="pct-${key}">—</span>
        </div>
        <input type="range" min="0" max="10" step="1" value="${state.weights[key]}" data-weight="${esc(key)}">
      </div>`;
    })
    .join('');

  $$('#weights input[type="range"]').forEach((slider) => {
    slider.oninput = () => {
      state.weights[slider.dataset.weight] = Number(slider.value);
      $$('.preset').forEach((p) => p.classList.remove('active'));
      updateWeightLabels();
    };
  });

  $$('.preset').forEach((button) => {
    button.onclick = () => {
      const preset = PRESETS[button.dataset.preset];
      const isBalanced = Object.keys(preset).length === 0;
      keys.forEach((key) => {
        state.weights[key] = isBalanced ? 5 : (preset[key] ?? 0);
      });
      $$('#weights input[type="range"]').forEach((slider) => {
        slider.value = state.weights[slider.dataset.weight];
      });
      $$('.preset').forEach((p) => p.classList.toggle('active', p === button));
      updateWeightLabels();
      runRecommend();
    };
  });

  updateWeightLabels();
}

function updateWeightLabels() {
  const total = Object.values(state.weights).reduce((sum, value) => sum + value, 0);
  Object.entries(state.weights).forEach(([key, value]) => {
    const rawNode = $(`#raw-${key}`);
    const pctNode = $(`#pct-${key}`);
    if (rawNode) rawNode.textContent = value;
    if (pctNode) {
      pctNode.textContent = total && value ? `${((value / total) * 100).toFixed(0)}%` : '—';
    }
  });
}

async function runRecommend() {
  const container = $('#rec-results');
  container.innerHTML = skeletons(3);

  const weights = Object.fromEntries(
    Object.entries(state.weights).filter(([, value]) => value > 0)
  );

  const payload = {
    weights,
    top_k: 10,
    min_reviews: Number($('#min-reviews').value) || 0,
    apply_shrinkage: true,
  };
  const budgetMin = $('#budget-min').value;
  const budgetMax = $('#budget-max').value;
  if (budgetMin !== '') payload.budget_min = Number(budgetMin);
  if (budgetMax !== '') payload.budget_max = Number(budgetMax);

  try {
    const response = await api('/recommend', { method: 'POST', body: JSON.stringify(payload) });
    if (!response.results.length) {
      let hint =
        'No phone passed your filters (min reviews / price). Try min reviews = 0 and clear the price fields.';
      try {
        const stats = await api('/stats');
        if (!stats.phones) {
          hint =
            'The database has no phones yet. Wait for <code class="mono">ingest-hf</code> to finish ' +
            'keeping phones, or run it again.';
        } else if (!stats.aspect_sentiments) {
          hint =
            `There are ${stats.phones} phone(s) but no aspect scores yet. ` +
            'Let ingest finish (or run <code class="mono">python run.py analyze</code>), then click Rank again.';
        } else if (response.candidates_considered === 0) {
          hint =
            `Database has ${stats.phones} phone(s), but none match min reviews = ${payload.min_reviews}` +
            (payload.budget_min != null || payload.budget_max != null ? ' / your budget' : '') +
            '. Lower the minimum or clear price filters.';
        }
      } catch { /* keep default hint */ }
      container.innerHTML = emptyState('No phones to rank', hint);
      return;
    }

    container.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="row wrap small">
          <span class="dim">Ranked ${response.results.length} of ${response.candidates_considered}</span>
          ${Object.entries(response.weights_used)
            .sort((a, b) => b[1] - a[1])
            .map(([key, value]) => `<span class="chip info">${esc(key)} ${(value * 100).toFixed(0)}%</span>`)
            .join('')}
        </div>
      </div>
      ${response.results.map(renderRecommendation).join('')}`;
  } catch (error) {
    container.innerHTML = '';
    toast('Recommendation failed', error.message, 'err');
  }
}

function renderRecommendation(item) {
  const rows = item.breakdown
    .filter((c) => c.weight > 0)
    .map(
      (c) => `<div class="bar-row" style="grid-template-columns:120px 1fr 92px">
        <span class="bar-name">${esc(c.aspect)}</span>
        <span class="bar-track"><span class="bar-fill"
          style="width:${(c.score ?? 0) * 100}%;background:${scoreColor(c.score)}"></span></span>
        <span class="bar-val">${score2(c.score)} <span class="dim">×${score2(c.weight)}</span></span>
      </div>`
    )
    .join('');

  const amazonRating = starRatingMarkup(item.site_rating, item.site_rating_count);

  return `<div class="rec ${item.rank === 1 ? 'top' : ''}">
    <div class="rec-layout">
      ${phoneImageMarkup(item, 'rec-size')}
      <div class="rec-body">
        <div class="rec-head">
          <div class="rank">${item.rank}</div>
          <div style="min-width:0;flex:1">
            <div class="phone-name">${esc(item.name)}</div>
            <div class="phone-meta">${esc(item.brand || 'Unknown')}</div>
            ${amazonRating ? `<div class="phone-rating-row">${amazonRating}</div>` : ''}
            <div class="phone-meta">${money(item.price, item.currency)} · ${num(item.review_count)} analysed reviews</div>
          </div>
          <div class="rec-score">
            <div class="rec-score-val" style="color:${scoreColor(item.final_score)}">${item.final_score.toFixed(3)}</div>
            <div class="rec-score-lbl">match score</div>
          </div>
        </div>
        <div class="mt-16">${rows}</div>
        <div class="row wrap mt-16">
          ${item.strengths.map((s) => `<span class="chip pos">▲ ${esc(s)}</span>`).join('')}
          ${item.weaknesses.map((w) => `<span class="chip neg">▼ ${esc(w)}</span>`).join('')}
          <div class="spacer"></div>
          <button class="btn btn-sm btn-ghost" onclick="openPhone(${item.smartphone_id})">Details →</button>
        </div>
      </div>
    </div>
  </div>`;
}

async function renderPhones() {
  const grid = $('#phone-grid');
  grid.innerHTML = skeletons(4);
  const query = $('#phone-search').value.trim();
  const brand = $('#phone-brand').value;
  const params = new URLSearchParams({ limit: '200' });
  if (query) params.set('q', query);
  if (brand) params.set('brand', brand);

  try {
    const [list, features] = await Promise.all([
      api(`/phones?${params}`),
      state.features.length ? Promise.resolve(state.features) : api('/features'),
    ]);
    state.features = features;
    $('#phone-count').textContent = `${list.total} phone(s)`;

    if (!list.items.length) {
      grid.innerHTML = emptyState(
        'No phones in the database',
        'Run <code class="mono">python run.py ingest-hf</code> then refresh.'
      );
      return;
    }

    const byId = Object.fromEntries(features.map((f) => [f.smartphone_id, f]));
    const aspects = state.aspects.map((a) => a.aspect);

    grid.innerHTML = list.items
      .map((phone) => {
        const vector = byId[phone.id];
        const bars = aspects
          .map((aspect) => {
            const value = vector?.scores[aspect];
            return `<div class="bar-row" style="grid-template-columns:78px 1fr 38px;margin-bottom:6px">
              <span class="bar-name">${esc(aspect)}</span>
              <span class="bar-track"><span class="bar-fill"
                style="width:${(value ?? 0) * 100}%;background:${scoreColor(value) || 'var(--surface-3)'}"></span></span>
              <span class="bar-val" style="font-size:11px">${score2(value)}</span>
            </div>`;
          })
          .join('');
        return `<div class="phone-card" onclick="openPhone(${phone.id})">
          ${phoneImageMarkup(phone, 'card-size')}
          <div class="phone-card-body">
            <div class="phone-name truncate" title="${esc(phoneLabel(phone))}">${esc(phoneLabel(phone))}</div>
            <div class="phone-meta">${esc(phone.brand || 'Unknown')}</div>
            ${phone.site_rating != null ? `<div class="phone-rating-row">${starRatingMarkup(phone.site_rating, phone.site_rating_count)}</div>` : ''}
            <div class="phone-price">${money(phone.latest_price, phone.currency)}</div>
            <div class="phone-meta">${num(phone.analyzed_review_count)} analysed reviews</div>
            ${bars}
          </div>
        </div>`;
      })
      .join('');
  } catch (error) {
    grid.innerHTML = '';
    toast('Could not load phones', error.message, 'err');
  }
}

async function openPhone(phoneId) {
  $('#drawer-body').innerHTML = skeletons(2);
  $('#drawer').classList.add('open');
  $('#drawer-backdrop').classList.add('open');

  try {
    const phone = await api(`/phones/${phoneId}`);
    $('#drawer-title').textContent = phoneLabel(phone);
    const ratingLine = phone.site_rating != null
      ? ` · ${phone.site_rating.toFixed(1)}★ (${num(phone.site_rating_count)})`
      : '';
    $('#drawer-sub').textContent =
      `${phone.brand || 'Unknown'} · ${money(phone.latest_price, phone.currency)} · ` +
      `${num(phone.analyzed_review_count)} analysed reviews${ratingLine}`;

    const hero = phone.image_url
      ? `<div class="drawer-hero">${phoneImageMarkup(phone, 'drawer-size')}</div>`
      : '';

    const breakdown = phone.aspect_scores.length
      ? phone.aspect_scores
          .map(
            (s) => `<div style="margin-bottom:14px">
        <div class="row" style="margin-bottom:6px">
          <strong class="cap">${esc(s.aspect)}</strong>
          <span class="dim small">${num(s.mention_count)} mentions</span>
          <div class="spacer"></div>
          <span class="mono" style="color:${scoreColor(s.score)}"><strong>${score2(s.score)}</strong></span>
        </div>
        <div class="stacked" style="height:16px">
          ${s.positive_count ? `<div style="width:${(s.positive_count / s.mention_count) * 100}%;background:var(--positive)"></div>` : ''}
          ${s.neutral_count ? `<div style="width:${(s.neutral_count / s.mention_count) * 100}%;background:var(--neutral)"></div>` : ''}
          ${s.negative_count ? `<div style="width:${(s.negative_count / s.mention_count) * 100}%;background:var(--negative)"></div>` : ''}
        </div>
      </div>`
          )
          .join('')
      : '<p class="dim small">No aspect scores yet — run analyze.</p>';

    $('#drawer-body').innerHTML = `${hero}<div>${breakdown}</div>
      <p class="card-note mt-16">Scores come from review sentences already stored in the database.</p>`;
  } catch (error) {
    $('#drawer-body').innerHTML = `<div class="banner">${esc(error.message)}</div>`;
  }
}

function closeDrawer() {
  $('#drawer').classList.remove('open');
  $('#drawer-backdrop').classList.remove('open');
}

async function loadPhoneSelectors() {
  try {
    const brands = await api('/phones/meta/brands');
    const brandNode = $('#phone-brand');
    const current = brandNode.value;
    brandNode.innerHTML =
      `<option value="">All brands</option>` +
      brands.map((b) => `<option value="${esc(b.brand)}">${esc(b.brand)} (${b.phones})</option>`).join('');
    brandNode.value = current;
  } catch { /* optional */ }
}

const currentView = () => (location.hash || '#recommend').slice(1).split('?')[0];
function go(view) { location.hash = view; }

async function renderView(view) {
  if (!VIEW_META[view]) view = 'recommend';
  $$('.view').forEach((node) => node.classList.toggle('active', node.id === `view-${view}`));
  $$('.nav-item').forEach((node) => node.classList.toggle('active', node.dataset.view === view));
  const [title, subtitle] = VIEW_META[view];
  $('#page-title').textContent = title;
  $('#page-sub').textContent = subtitle;
  $('#sidebar').classList.remove('open');

  if (view === 'recommend') return runRecommend();
  if (view === 'phones') return renderPhones();
}

async function refreshAll() {
  state.features = [];
  await Promise.all([loadHealth(), loadBadges(), loadPhoneSelectors()]);
  await renderView(currentView());
}

async function init() {
  try {
    state.aspects = await api('/aspects');
  } catch {
    state.aspects = ['battery', 'camera', 'display', 'performance', 'price'].map((a) => ({
      aspect: a, label: a,
    }));
  }

  renderWeightControls();
  await Promise.all([loadHealth(), loadBadges(), loadPhoneSelectors()]);

  $$('.nav-item').forEach((node) => { node.onclick = () => go(node.dataset.view); });
  window.addEventListener('hashchange', () => renderView(currentView()));
  $('#btn-refresh').onclick = refreshAll;
  $('#btn-theme').onclick = toggleTheme;
  initTheme();
  $('#menu-toggle').onclick = () => $('#sidebar').classList.toggle('open');
  $('#btn-recommend').onclick = runRecommend;

  let searchTimer;
  $('#phone-search').oninput = () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(renderPhones, 280);
  };
  $('#phone-brand').onchange = renderPhones;

  $('#drawer-close').onclick = closeDrawer;
  $('#drawer-backdrop').onclick = closeDrawer;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });

  await renderView(currentView());
}

window.go = go;
window.openPhone = openPhone;
init();
