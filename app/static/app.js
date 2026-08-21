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

const state = {
  aspects: [],
  health: null,
  features: [],
  weights: {},
};

const VIEW_META = {
  recommend: ['Recommend', 'Set your priorities and get ranked phones from the database'],
  phones: ['Phones', 'Browse phones already stored in the database'],
  data: ['Database', 'What is currently loaded — refresh data from the CLI'],
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

  return `<div class="rec ${item.rank === 1 ? 'top' : ''}">
    <div class="rec-head">
      <div class="rank">${item.rank}</div>
      <div style="min-width:0">
        <div class="phone-name">${esc(item.name)}</div>
        <div class="phone-meta">${esc(item.brand || 'Unknown')} · ${money(item.price, item.currency)} · ${num(item.review_count)} reviews</div>
      </div>
      <div class="rec-score">
        <div class="rec-score-val" style="color:${scoreColor(item.final_score)}">${item.final_score.toFixed(3)}</div>
        <div class="rec-score-lbl">score</div>
      </div>
    </div>
    <div class="mt-16">${rows}</div>
    <div class="row wrap mt-16">
      ${item.strengths.map((s) => `<span class="chip pos">▲ ${esc(s)}</span>`).join('')}
      ${item.weaknesses.map((w) => `<span class="chip neg">▼ ${esc(w)}</span>`).join('')}
      <div class="spacer"></div>
      <button class="btn btn-sm btn-ghost" onclick="openPhone(${item.smartphone_id})">Details →</button>
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
          <div class="phone-card-head">
            <div style="min-width:0;flex:1">
              <div class="phone-name">${esc(phone.canonical_name || phone.raw_title || 'Unknown')}</div>
              <div class="phone-meta">${esc(phone.brand || 'Unknown')} · ${num(phone.analyzed_review_count)} analysed</div>
            </div>
            <div class="phone-price">${money(phone.latest_price, phone.currency)}</div>
          </div>
          ${bars}
        </div>`;
      })
      .join('');
  } catch (error) {
    grid.innerHTML = '';
    toast('Could not load phones', error.message, 'err');
  }
}

async function renderData() {
  $('#stat-cards').innerHTML = skeletons(4);
  try {
    const [stats, features] = await Promise.all([api('/stats'), api('/features')]);
    state.features = features;
    setBadges(stats);

    $('#stat-cards').innerHTML = `
      <div class="stat"><div class="stat-label">Phones</div><div class="stat-value">${num(stats.phones)}</div><div class="stat-sub">${(stats.sources || []).join(', ') || '—'}</div></div>
      <div class="stat pos"><div class="stat-label">Usable reviews</div><div class="stat-value">${num(stats.reviews_usable)}</div><div class="stat-sub">of ${num(stats.reviews_total)}</div></div>
      <div class="stat"><div class="stat-label">Sentences</div><div class="stat-value">${num(stats.sentences)}</div></div>
      <div class="stat neu"><div class="stat-label">Aspect mentions</div><div class="stat-value">${num(stats.aspect_sentiments)}</div></div>`;

    if (!features.length) {
      $('#feature-table').innerHTML = emptyState(
        'No scores yet',
        'After ingest, run <code class="mono">python run.py analyze</code> (or use <code class="mono">ingest-hf</code> with analyze on).'
      );
      return;
    }

    const aspects = state.aspects.map((a) => a.aspect);
    const head = `<tr><th>Phone</th><th class="num">Price</th>${aspects.map((a) => `<th class="num cap">${esc(a)}</th>`).join('')}<th class="num">Reviews</th></tr>`;
    const body = features
      .map((vector) => {
        const cells = aspects
          .map((aspect) => {
            const value = vector.scores[aspect];
            if (value == null) return `<td class="num"><span class="heat empty">n/a</span></td>`;
            return `<td class="num"><span class="heat" style="background:${scoreColor(value)}">${score2(value)}</span></td>`;
          })
          .join('');
        return `<tr class="clickable" onclick="openPhone(${vector.smartphone_id})">
          <td><strong>${esc(vector.name)}</strong></td>
          <td class="num">${money(vector.price, vector.currency)}</td>
          ${cells}
          <td class="num">${num(vector.review_count)}</td>
        </tr>`;
      })
      .join('');
    $('#feature-table').innerHTML = `<div class="table-wrap"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
  } catch (error) {
    toast('Could not load database status', error.message, 'err');
  }
}

async function openPhone(phoneId) {
  $('#drawer-body').innerHTML = skeletons(2);
  $('#drawer').classList.add('open');
  $('#drawer-backdrop').classList.add('open');

  try {
    const phone = await api(`/phones/${phoneId}`);
    $('#drawer-title').textContent = phone.canonical_name || phone.raw_title || `Phone ${phoneId}`;
    $('#drawer-sub').textContent =
      `${phone.brand || 'Unknown'} · ${money(phone.latest_price, phone.currency)} · ` +
      `${num(phone.analyzed_review_count)} analysed reviews`;

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

    $('#drawer-body').innerHTML = `<div>${breakdown}</div>
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
  if (view === 'data') return renderData();
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
