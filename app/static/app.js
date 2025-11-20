const state = { page: 1, pageSize: 10, filters: { sku: '', name: '', description: '', active: '' } };

// -------- Upload --------
const uploadForm = document.getElementById('upload-form');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const progressError = document.getElementById('progress-error');

uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('csvFile');
  if (!fileInput.files[0]) return alert('Select a CSV file');
  progressError.style.display = 'none';
  progressText.textContent = 'Uploading...';
  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  const res = await fetch('/upload', { method: 'POST', body: fd });
  if (!res.ok) { progressError.textContent = await res.text(); progressError.style.display = 'block'; return; }
  const job = await res.json();
  progressText.textContent = 'Queued';
  const es = new EventSource(`/jobs/${job.id}/events`);
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    const { stage, status, processed_rows, total_rows, error_message } = data;
    const pct = total_rows > 0 ? Math.floor((processed_rows / total_rows) * 100) : 0;
    progressBar.style.width = `${pct}%`;
    progressText.textContent = `${stage} — ${pct}% (${processed_rows}/${total_rows})`;
    if (status === 'failed') { progressError.textContent = error_message || 'Import failed'; progressError.style.display = 'block'; es.close(); }
    if (status === 'completed') { progressText.textContent = 'Import Complete'; es.close(); loadProducts(); }
  };
  es.onerror = () => { /* ignore transient errors */ };
});

// -------- Products --------
const tbody = document.querySelector('#products-table tbody');
const pageInfo = document.getElementById('page-info');

document.getElementById('refresh-products').addEventListener('click', () => loadProducts());
document.getElementById('apply-filters').addEventListener('click', () => {
  state.filters.sku = document.getElementById('filter-sku').value;
  state.filters.name = document.getElementById('filter-name').value;
  state.filters.description = document.getElementById('filter-description').value;
  state.filters.active = document.getElementById('filter-active').value;
  state.page = 1; loadProducts();
});

document.getElementById('prev-page').addEventListener('click', () => { if (state.page > 1) { state.page--; loadProducts(); } });
document.getElementById('next-page').addEventListener('click', () => { state.page++; loadProducts(); });

document.getElementById('bulk-delete').addEventListener('click', async () => {
  if (!confirm('Are you sure? This cannot be undone.')) return;
  const res = await fetch('/products', { method: 'DELETE' });
  if (res.ok) { alert('All products deleted'); loadProducts(); }
});

async function loadProducts(){
  const params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
  if (state.filters.sku) params.append('sku', state.filters.sku);
  if (state.filters.name) params.append('name', state.filters.name);
  if (state.filters.description) params.append('description', state.filters.description);
  if (state.filters.active !== '') params.append('active', state.filters.active);
  const res = await fetch(`/products?${params.toString()}`);
  const data = await res.json();
  tbody.innerHTML = '';
  data.items.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${p.id}</td><td>${p.sku}</td><td>${p.name}</td><td>${p.active ? 'Yes' : 'No'}</td><td>${p.description || ''}</td>
      <td>
        <button data-action="edit" data-id="${p.id}" class="btn">Edit</button>
        <button data-action="delete" data-id="${p.id}" class="btn btn-danger">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  });
  pageInfo.textContent = `Page ${data.page} • ${data.total} total`;
}

tbody.addEventListener('click', async (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  const id = btn.getAttribute('data-id');
  const action = btn.getAttribute('data-action');
  if (action === 'delete') {
    if (!confirm('Delete this product?')) return;
    const res = await fetch(`/products/${id}`, { method: 'DELETE' });
    if (res.ok) loadProducts();
  }
  if (action === 'edit') {
    const row = btn.closest('tr').children;
    document.getElementById('edit-id').value = id;
    document.getElementById('edit-sku').value = row[1].textContent;
    document.getElementById('edit-name').value = row[2].textContent;
    document.getElementById('edit-active').checked = row[3].textContent === 'Yes';
    document.getElementById('edit-description').value = row[4].textContent;
  }
});

document.getElementById('reset-editor').addEventListener('click', () => { document.getElementById('edit-id').value=''; document.getElementById('edit-sku').value=''; document.getElementById('edit-name').value=''; document.getElementById('edit-description').value=''; document.getElementById('edit-active').checked=true; });

document.getElementById('save-product').addEventListener('click', async () => {
  const id = document.getElementById('edit-id').value;
  const payload = {
    sku: document.getElementById('edit-sku').value,
    name: document.getElementById('edit-name').value,
    description: document.getElementById('edit-description').value,
    active: document.getElementById('edit-active').checked,
  };
  if (!payload.sku || !payload.name) return alert('SKU and Name are required');
  let res;
  if (id) {
    res = await fetch(`/products/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  } else {
    res = await fetch(`/products`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  }
  if (!res.ok) { alert(await res.text()); return; }
  loadProducts();
});

// -------- Webhooks --------
const whTbody = document.querySelector('#webhooks-table tbody');

document.getElementById('refresh-webhooks').addEventListener('click', loadWebhooks);

document.getElementById('reset-webhook').addEventListener('click', () => { document.getElementById('wh-id').value=''; document.getElementById('wh-url').value=''; document.getElementById('wh-event').value='import.completed'; document.getElementById('wh-enabled').checked=true; });

document.getElementById('save-webhook').addEventListener('click', async () => {
  const id = document.getElementById('wh-id').value;
  const payload = {
    url: document.getElementById('wh-url').value,
    event: document.getElementById('wh-event').value,
    enabled: document.getElementById('wh-enabled').checked,
  };
  let res;
  if (id) {
    res = await fetch(`/webhooks/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  } else {
    res = await fetch(`/webhooks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  }
  if (!res.ok) { alert(await res.text()); return; }
  loadWebhooks();
});

whTbody.addEventListener('click', async (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  const id = btn.getAttribute('data-id');
  const action = btn.getAttribute('data-action');
  if (action === 'edit') {
    const row = btn.closest('tr').children;
    document.getElementById('wh-id').value = id;
    document.getElementById('wh-url').value = row[1].textContent;
    document.getElementById('wh-event').value = row[2].textContent;
    document.getElementById('wh-enabled').checked = row[3].textContent === 'Yes';
  }
  if (action === 'delete') {
    if (!confirm('Delete this webhook?')) return;
    const res = await fetch(`/webhooks/${id}`, { method: 'DELETE' });
    if (res.ok) loadWebhooks();
  }
  if (action === 'test') {
    const res = await fetch(`/webhooks/${id}/test`, { method: 'POST' });
    const json = await res.json();
    alert(JSON.stringify(json));
    loadWebhooks();
  }
});

async function loadWebhooks(){
  const res = await fetch('/webhooks');
  const items = await res.json();
  whTbody.innerHTML = '';
  items.forEach(w => {
    const tr = document.createElement('tr');
    const last = w.last_status_code ? `${w.last_status_code} • ${w.last_response_ms || '-'}ms` : '-';
    tr.innerHTML = `<td>${w.id}</td><td>${w.url}</td><td>${w.event}</td><td>${w.enabled ? 'Yes' : 'No'}</td><td>${last}</td>
      <td>
        <button data-action="edit" data-id="${w.id}" class="btn">Edit</button>
        <button data-action="test" data-id="${w.id}" class="btn">Test</button>
        <button data-action="delete" data-id="${w.id}" class="btn btn-danger">Delete</button>
      </td>`;
    whTbody.appendChild(tr);
  });
}

// Initial load
loadProducts();
loadWebhooks();