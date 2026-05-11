// ===== ESTADO GLOBAL =====
let archivosSeleccionados = new DataTransfer();
let resultadoActual = null;
let todosHallazgos = [];

// ===== NAVEGACIÓN =====
function mostrarSeccion(seccion) {
  ['nueva', 'resultado', 'historial'].forEach(s => {
    const el = document.getElementById(`sec-${s}`);
    if (el) el.style.display = 'none';
  });
  const target = document.getElementById(`sec-${seccion}`);
  if (target) target.style.display = 'block';

  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const btn = [...document.querySelectorAll('.nav-btn')].find(b => b.textContent.toLowerCase().includes(seccion === 'nueva' ? 'nueva' : 'historial'));
  if (btn) btn.classList.add('active');

  if (seccion === 'historial') cargarHistorial();
}

// ===== MANEJO DE ARCHIVOS =====
function triggerUpload(tipo) {
  document.getElementById(`input-${tipo}`).click();
}

function asignarArchivo(tipo, input) {
  const files = input.files;
  if (!files.length) return;
  for (const f of files) {
    archivosSeleccionados.items.add(f);
  }
  const slot = document.getElementById(`slot-${tipo}`);
  const status = document.getElementById(`status-${tipo}`);
  if (slot) slot.classList.add('loaded');
  if (status) status.textContent = [...files].map(f => f.name).join(', ');
  actualizarListaArchivos();
}

function agregarArchivosGenerales(input) {
  const files = input.files;
  if (!files.length) return;
  for (const f of files) {
    archivosSeleccionados.items.add(f);
  }
  actualizarListaArchivos();
}

function actualizarListaArchivos() {
  const lista = document.getElementById('lista-archivos');
  lista.innerHTML = '';
  const files = archivosSeleccionados.files;
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const tag = document.createElement('div');
    tag.className = 'archivo-tag';
    tag.innerHTML = `<span>📄 ${f.name}</span><span class="remove" onclick="removerArchivo(${i})">✕</span>`;
    lista.appendChild(tag);
  }
}

function removerArchivo(index) {
  const nuevo = new DataTransfer();
  const files = archivosSeleccionados.files;
  for (let i = 0; i < files.length; i++) {
    if (i !== index) nuevo.items.add(files[i]);
  }
  archivosSeleccionados = nuevo;
  actualizarListaArchivos();
}

// Drag & Drop
function dragOver(e) {
  e.preventDefault();
  document.getElementById('dropzone').classList.add('over');
}
function dragLeave(e) {
  document.getElementById('dropzone').classList.remove('over');
}
function dropArchivos(e) {
  e.preventDefault();
  document.getElementById('dropzone').classList.remove('over');
  const files = e.dataTransfer.files;
  for (const f of files) archivosSeleccionados.items.add(f);
  actualizarListaArchivos();
}

// Click en dropzone
document.addEventListener('DOMContentLoaded', () => {
  const dz = document.getElementById('dropzone');
  if (dz) {
    dz.addEventListener('click', (e) => {
      if (e.target.closest('.archivo-tag')) return;
      document.getElementById('input-general').click();
    });
  }
});

// ===== INICIAR REVISIÓN =====
async function iniciarRevision(e) {
  e.preventDefault();

  const files = archivosSeleccionados.files;
  if (files.length === 0) {
    alert('Por favor carga al menos un documento para analizar.');
    return;
  }

  const referencia = document.getElementById('referencia').value || '';
  const cliente = document.getElementById('cliente').value || '';

  mostrarLoading(true);
  animarSteps();

  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
  }
  if (referencia) formData.append('referencia', referencia);
  if (cliente) formData.append('cliente', cliente);

  try {
    const res = await fetch('/api/revision', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Error del servidor');
    }

    const data = await res.json();
    mostrarLoading(false);
    mostrarResultado(data);
  } catch (err) {
    mostrarLoading(false);
    alert(`Error al procesar: ${err.message}`);
  }
}

// ===== MOSTRAR RESULTADO =====
function mostrarResultado(data) {
  resultadoActual = data;
  todosHallazgos = data.hallazgos || [];

  // Semáforo
  const card = document.getElementById('semaforo-card');
  card.className = `semaforo-card ${data.semaforo}`;

  const emojis = { verde: '✅', amarillo: '⚠️', rojo: '🚫', negro: '⛔' };
  const titulos = {
    verde: 'PUEDE VALIDAR',
    amarillo: 'REVISAR ANTES DE VALIDAR',
    rojo: 'NO VALIDAR',
    negro: 'RIESGO GRAVE — ESCALAR'
  };

  document.getElementById('semaforo-luz').textContent = emojis[data.semaforo] || '⚠️';
  document.getElementById('semaforo-titulo').textContent = titulos[data.semaforo] || 'Resultado';
  document.getElementById('semaforo-recomendacion').textContent = data.recomendacion;
  document.getElementById('meta-ref').textContent = `Ref: ${data.referencia}`;
  document.getElementById('meta-fecha').textContent = data.fecha_revision;

  document.getElementById('cnt-critico').textContent = data.total_criticos;
  document.getElementById('cnt-alto').textContent = data.total_altos;
  document.getElementById('cnt-medio').textContent = data.total_medios;
  document.getElementById('cnt-bajo').textContent = data.total_bajos;

  // Documentos analizados
  const docsDiv = document.getElementById('docs-analizados');
  docsDiv.innerHTML = (data.documentos_cargados || []).map(d =>
    `<div class="doc-tag">📄 ${d}</div>`
  ).join('');

  // Renderizar tabla
  renderizarTabla(todosHallazgos);

  mostrarSeccion('resultado');
  window.scrollTo(0, 0);
}

function renderizarTabla(hallazgos) {
  const tbody = document.getElementById('tbody-hallazgos');
  const sinHallazgos = document.getElementById('sin-hallazgos');
  tbody.innerHTML = '';

  if (!hallazgos || hallazgos.length === 0) {
    sinHallazgos.style.display = 'block';
    return;
  }
  sinHallazgos.style.display = 'none';

  hallazgos.forEach(h => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${escHtml(h.campo)}</strong></td>
      <td>${escHtml(h.valor_pedimento)}</td>
      <td>${escHtml(h.valor_documento_fuente)}</td>
      <td>${escHtml(h.documento_fuente)}</td>
      <td style="font-size:11px;color:var(--text3)">${escHtml(h.fundamento_legal)}</td>
      <td><span class="badge ${escHtml(h.riesgo)}">${escHtml(h.riesgo)}</span></td>
      <td class="accion-text">${escHtml(h.accion_recomendada)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function filtrarHallazgos(nivel, btn) {
  document.querySelectorAll('.filtro-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  const filtrados = nivel === 'todos'
    ? todosHallazgos
    : todosHallazgos.filter(h => h.riesgo === nivel);
  renderizarTabla(filtrados);
}

// ===== HISTORIAL =====
async function cargarHistorial() {
  const div = document.getElementById('tabla-historial');
  div.innerHTML = '<p style="color:var(--text3);text-align:center;padding:20px">Cargando...</p>';
  try {
    const res = await fetch('/api/revisiones');
    const data = await res.json();
    if (!data.length) {
      div.innerHTML = '<p style="color:var(--text3);text-align:center;padding:30px">Sin revisiones guardadas.</p>';
      return;
    }
    div.innerHTML = `
      <table class="historial-table">
        <thead><tr>
          <th>ID</th><th>Referencia</th><th>Cliente</th><th>Fecha</th><th>Estatus</th>
        </tr></thead>
        <tbody>${data.map(r => `
          <tr onclick="verRevision('${r.id}')">
            <td><a class="hist-link">${r.id}</a></td>
            <td>${escHtml(r.referencia)}</td>
            <td>${escHtml(r.cliente)}</td>
            <td>${escHtml(r.fecha)}</td>
            <td>${escHtml(r.estatus)}</td>
          </tr>
        `).join('')}</tbody>
      </table>
    `;
  } catch (err) {
    div.innerHTML = `<p style="color:var(--critico);padding:20px">Error: ${err.message}</p>`;
  }
}

async function verRevision(id) {
  try {
    const res = await fetch(`/api/revision/${id}`);
    const data = await res.json();
    mostrarResultado(data);
  } catch (err) {
    alert(`No se pudo cargar la revisión: ${err.message}`);
  }
}

// ===== NUEVA REVISIÓN =====
function nuevaRevision() {
  archivosSeleccionados = new DataTransfer();
  document.getElementById('form-revision').reset();
  document.querySelectorAll('.doc-slot').forEach(s => s.classList.remove('loaded'));
  document.querySelectorAll('.doc-status').forEach(s => s.textContent = 'Sin cargar');
  document.getElementById('lista-archivos').innerHTML = '';
  resultadoActual = null;
  todosHallazgos = [];
  mostrarSeccion('nueva');
}

// ===== EXPORTAR =====
async function exportarPDF() {
  if (!resultadoActual) return;

  // Intentar cargar el logo como base64
  let logoHtml = '<div style="font-size:22px;font-weight:700;color:#CC1F2F;letter-spacing:1px">CIE</div>';
  try {
    const resp = await fetch('/static/img/cie-logo.png');
    if (resp.ok) {
      const blob = await resp.blob();
      const dataUrl = await new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsDataURL(blob);
      });
      logoHtml = `<img src="${dataUrl}" style="height:48px;object-fit:contain" alt="CIE">`;
    }
  } catch (_) {}

  const semColors = { verde: '#2ed573', amarillo: '#ffd32a', rojo: '#ff4757', negro: '#a29bfe' };
  const semNombres = { verde: 'PUEDE VALIDAR', amarillo: 'REVISAR', rojo: 'NO VALIDAR', negro: 'ESCALAR' };
  const color = semColors[resultadoActual.semaforo] || '#fff';

  let html = `<!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8">
    <title>Glosa ${resultadoActual.referencia}</title>
    <style>
      body{font-family:Arial,sans-serif;font-size:12px;color:#111;padding:0;max-width:1000px;margin:0 auto}
      .report-header{background:#1B2B6B;color:#fff;padding:18px 28px;display:flex;align-items:center;gap:20px;border-bottom:4px solid #CC1F2F}
      .report-header-text h1{font-size:18px;margin:0;font-weight:700;letter-spacing:.5px}
      .report-header-text p{margin:2px 0 0;font-size:11px;opacity:.8}
      .report-body{padding:24px}
      .sem{padding:10px 20px;border-radius:6px;font-weight:bold;font-size:14px;display:inline-block;margin:8px 0;color:#fff;background:${color}}
      table{width:100%;border-collapse:collapse;margin-top:16px;font-size:11px}
      th{background:#1B2B6B;color:#fff;padding:8px;text-align:left}
      td{padding:8px;border-bottom:1px solid #ddd;vertical-align:top}
      .c{color:#ff4757;font-weight:bold} .a{color:#e67e22;font-weight:bold}
      .m{color:#d4ac0d} .b{color:#27ae60}
      .meta{color:#666;font-size:11px;margin-bottom:16px}
      .footer{text-align:center;color:#999;font-size:10px;margin-top:24px;padding-top:12px;border-top:1px solid #eee}
    </style>
  </head><body>
    <div class="report-header">
      ${logoHtml}
      <div class="report-header-text">
        <h1>GLOSA Preventiva Aduanal</h1>
        <p>CIE Agencia Aduanal — Reporte de Revisión</p>
      </div>
    </div>
    <div class="report-body">
    <p class="meta">Referencia: <strong>${resultadoActual.referencia}</strong> &nbsp;|&nbsp; Fecha: ${resultadoActual.fecha_revision} &nbsp;|&nbsp; ID: ${resultadoActual.id}</p>
    <div class="sem">${semNombres[resultadoActual.semaforo]?.toUpperCase()}</div>
    <p style="margin:8px 0 16px">${resultadoActual.recomendacion}</p>
    <p><strong>Resumen:</strong> ${resultadoActual.total_criticos} críticos | ${resultadoActual.total_altos} altos | ${resultadoActual.total_medios} medios | ${resultadoActual.total_bajos} bajos</p>
    <table>
      <thead><tr><th>Campo</th><th>Valor Pedimento</th><th>Valor Documento</th><th>Doc. Fuente</th><th>Fundamento Legal</th><th>Riesgo</th><th>Acción</th></tr></thead>
      <tbody>`;

  (resultadoActual.hallazgos || []).forEach(h => {
    const cls = {Crítico:'c',Alto:'a',Medio:'m',Bajo:'b'}[h.riesgo] || '';
    html += `<tr>
      <td>${h.campo}</td>
      <td>${h.valor_pedimento}</td>
      <td>${h.valor_documento_fuente}</td>
      <td>${h.documento_fuente}</td>
      <td>${h.fundamento_legal}</td>
      <td class="${cls}">${h.riesgo}</td>
      <td>${h.accion_recomendada}</td>
    </tr>`;
  });

  html += `</tbody></table>
    <div class="footer">Generado por CIE GLOSA — Sistema de Glosa Preventiva Aduanal</div>
    </div>
  </body></html>`;

  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `Glosa_${resultadoActual.referencia}_${resultadoActual.id}.html`;
  a.click();
  URL.revokeObjectURL(url);
}

// ===== LOADING =====
function mostrarLoading(show) {
  document.getElementById('loading').style.display = show ? 'flex' : 'none';
}

function animarSteps() {
  const steps = ['step1','step2','step3','step4'];
  steps.forEach(s => {
    const el = document.getElementById(s);
    if (el) { el.classList.remove('active','done'); }
  });
  let i = 0;
  const avanzar = () => {
    if (i > 0 && i <= steps.length) {
      const prev = document.getElementById(steps[i-1]);
      if (prev) { prev.classList.remove('active'); prev.classList.add('done'); }
    }
    if (i < steps.length) {
      const cur = document.getElementById(steps[i]);
      if (cur) cur.classList.add('active');
      i++;
      setTimeout(avanzar, 2500);
    }
  };
  avanzar();
}

// ===== UTILIDADES =====
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}
