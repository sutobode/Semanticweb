const app = document.getElementById('app');
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = (path) => fetch(path).then(async (r) => { const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(data.error?.message || `HTTP ${r.status}`); return data; });

function loading() { app.innerHTML = '<p>Đang tải dữ liệu RDF…</p>'; }
function errorView(error) { app.innerHTML = `<div class="error"><h1>Không thể tải dữ liệu</h1><p>${esc(error.message)}</p><p>Kiểm tra Fuseki và explorer service đang chạy.</p></div>`; }
function badges(values) { return (values || []).map((v) => `<span class="badge">${esc(typeof v === 'string' ? v.split('/').pop() : v['@id'] || v['@value'])}</span>`).join(''); }

async function home() {
  loading();
  try {
    const stats = await api('/api/stats');
    app.innerHTML = `<section class="hero"><h1>Khám phá Di sản Văn hóa Việt Nam</h1><p>Trải nghiệm VietHeritageLOD qua tìm kiếm, RDF/JSON-LD và các competency questions — không cần viết SPARQL.</p><div class="actions"><a class="button" href="#/search">Bắt đầu tìm kiếm</a><a class="button" href="#/queries">Xem competency questions</a></div></section><section class="grid"><div class="card"><div class="metric">${stats.total_entities}</div><div>Entities trong RDF graph</div></div><div class="card"><div class="metric">${stats.verified_external_links}</div><div>Verified external links</div></div><div class="card"><div class="metric">${stats.classes?.length || 0}</div><div>Ontology types có dữ liệu</div></div><div class="card"><div class="metric">${stats.categories?.length || 0}</div><div>Registry categories</div></div></section><section class="card" style="margin-top:1rem"><h2>Semantic Web access</h2><p>API: <a href="/docs">/docs</a> · SPARQL: <a href="http://localhost:3030/vietheritage/sparql" target="_blank" rel="noopener">Fuseki endpoint</a> · Dataset: <code>${esc(stats['@id'])}</code></p></section>`;
  } catch (e) { errorView(e); }
}

async function search() {
  loading();
  app.innerHTML = `<h1>Tìm kiếm di sản</h1><form id="search-form"><label>Từ khóa<label><input name="q" placeholder="Ví dụ: Huế, Hội An"></label></label><label>Loại entity<select name="entity_type"><option value="">Tất cả</option><option>HeritageSite</option><option>IntangibleHeritage</option><option>NationalTreasure</option><option>Museum</option><option>HistoricalPerson</option></select></label><label>Category<input name="registry_category" placeholder="world_heritage"></label><label>Năm<input name="year" inputmode="numeric" placeholder="1999"></label><button>Tìm kiếm</button></form><div id="results"></div>`;
  const form = document.getElementById('search-form');
  const run = async (page = 1) => { const params = new URLSearchParams(new FormData(form)); params.set('page', page); params.set('page_size', '25'); const results = document.getElementById('results'); results.innerHTML = '<p>Đang truy vấn RDF graph…</p>'; try { const data = await api(`/api/search?${params}`); results.innerHTML = `<p>${data.total} kết quả · trang ${data.page}</p><div class="result-list">${data.items.map(item => `<article class="card"><a href="#/entity/${encodeURIComponent(item['@id'].split('/').pop())}">${esc(item.label?.['@value'] || item['@id'])}</a><p>${badges(item['@type'])} ${badges(item.category)}</p><p>${esc(item.location || '')} ${esc(item.year || '')}</p><p class="uri">${esc(item['@id'])}</p></article>`).join('') || '<p class="empty">Không có kết quả.</p>'}</div>${data.page > 1 || data.has_next ? `<div class="actions">${data.page > 1 ? `<button id="previous">← Trang trước</button>` : ''}${data.has_next ? `<button id="next">Trang sau →</button>` : ''}</div>` : ''}`; document.getElementById('previous')?.addEventListener('click', () => run(data.page - 1)); document.getElementById('next')?.addEventListener('click', () => run(data.page + 1)); } catch (e) { results.innerHTML = `<div class="error">${esc(e.message)}</div>`; } };
  form.addEventListener('submit', (e) => { e.preventDefault(); run(1); });
  run(1);
}

async function entity(entityId) {
  loading();
  try { const data = await api(`/api/entities/${encodeURIComponent(entityId)}`); app.innerHTML = `<article><p><a href="#/search">← Quay lại tìm kiếm</a></p><h1>${esc(data.label?.[0]?.['@value'] || entityId)}</h1><p class="uri">${esc(data['@id'])}</p><div class="actions"><a class="button" href="/resource/${encodeURIComponent(entityId)}" target="_blank">HTML resource</a><a class="button" href="/resource/${encodeURIComponent(entityId)}" target="_blank" data-accept="turtle">Turtle qua API</a></div><section class="card"><h2>Ontology types</h2><p>${badges(data['@type'])}</p><h2>Mô tả</h2><p>${data.description?.map(x => esc(x['@value'])).join('<br>') || 'Chưa có mô tả.'}</p><h2>Categories</h2><p>${badges(data.categories)}</p><h2>Provenance</h2><ul>${data.sources?.map(x => `<li><a href="${esc(x)}" rel="prov:wasDerivedFrom">${esc(x)}</a></li>`).join('') || '<li>Chưa có source.</li>'}</ul><h2>Verified external links</h2><ul>${data.external_links?.map(x => `<li><a href="${esc(x['@id'])}" rel="owl:sameAs">${esc(x['@id'])}</a></li>`).join('') || '<li>Không có.</li>'}</section></article>`; } catch (e) { errorView(e); }
}

async function queries() {
  loading();
  try { const data = await api('/api/queries'); app.innerHTML = `<h1>Competency Questions</h1><p>Đây là các query SPARQL read-only đã được allowlist.</p><div class="result-list">${data.items.map(q => `<article class="card"><h2>${esc(q.id)} — ${esc(q.title)}</h2><p>${esc(q.description)}</p><button data-query="${esc(q.id)}">Chạy query</button><div id="output-${esc(q.id)}"></div></article>`).join('')}</div>`; document.querySelectorAll('[data-query]').forEach(button => button.addEventListener('click', async () => { const id = button.dataset.query; const out = document.getElementById(`output-${id}`); out.innerHTML = '<p>Đang chạy SPARQL…</p>'; try { const result = await api(`/api/queries/${id}/run`); out.innerHTML = `<pre>${esc(JSON.stringify(result.results, null, 2))}</pre>`; } catch (e) { out.innerHTML = `<div class="error">${esc(e.message)}</div>`; } })); } catch (e) { errorView(e); }
}

function route() { const hash = location.hash.slice(1) || '/'; if (hash === '/') return home(); if (hash === '/search') return search(); if (hash === '/queries') return queries(); if (hash.startsWith('/entity/')) return entity(decodeURIComponent(hash.slice('/entity/'.length))); return home(); }
window.addEventListener('hashchange', route); route();
