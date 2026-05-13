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

// ===== EXPORTAR PDF =====
async function exportarPDF() {
  if (!resultadoActual) return;

  // Cargar logo como base64
  let logoSrc = '';
  try {
    const resp = await fetch('/static/img/cie-logo.png');
    if (resp.ok) {
      const blob = await resp.blob();
      logoSrc = await new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsDataURL(blob);
      });
    }
  } catch (_) {}

  const semColors = { verde: '#2ed573', amarillo: '#f0a500', rojo: '#CC1F2F', negro: '#6c5ce7' };
  const semNombres = { verde: 'PUEDE VALIDAR', amarillo: 'REVISAR', rojo: 'NO VALIDAR', negro: 'ESCALAR' };
  const color = semColors[resultadoActual.semaforo] || '#888';

  // Construir filas de tabla
  let filas = '';
  (resultadoActual.hallazgos || []).forEach((h, i) => {
    const bgColor = { Crítico: '#fff5f5', Alto: '#fff8f0', Medio: '#fffef0', Bajo: '#f0fff4' }[h.riesgo] || '#fff';
    const riesgoColor = { Crítico: '#CC1F2F', Alto: '#e67e22', Medio: '#c49b0a', Bajo: '#27ae60' }[h.riesgo] || '#888';
    filas += `<tr style="background:${i%2===0?'#fff':bgColor}">
      <td style="font-weight:600;color:#1B2B6B">${h.campo}</td>
      <td>${h.valor_pedimento}</td>
      <td>${h.valor_documento_fuente}</td>
      <td style="color:#555">${h.documento_fuente}</td>
      <td style="font-size:9px;color:#666">${h.fundamento_legal}</td>
      <td style="text-align:center"><span style="background:${riesgoColor};color:#fff;padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700">${h.riesgo}</span></td>
      <td style="font-size:9px">${h.accion_recomendada}</td>
    </tr>`;
  });

  const logoTag = logoSrc
    ? `<img src="${logoSrc}" style="height:44px;object-fit:contain;display:block">`
    : `<span style="font-size:20px;font-weight:900;color:#CC1F2F">CIE</span>`;

  const contenido = `
    <div style="font-family:Arial,sans-serif;font-size:11px;color:#1a1a2e;background:#fff">
      <!-- HEADER -->
      <div style="background:#1B2B6B;display:flex;align-items:stretch;border-bottom:5px solid #CC1F2F;margin-bottom:20px">
        <div style="background:#fff;padding:12px 18px;display:flex;align-items:center;min-width:130px">${logoTag}</div>
        <div style="padding:12px 20px;color:#fff;flex:1">
          <div style="font-size:17px;font-weight:700;letter-spacing:.5px">Glosa Preventiva Aduanal</div>
          <div style="font-size:10px;opacity:.75;margin-top:2px">CIE Agencia Aduanal — Reporte de Revisión</div>
        </div>
        <div style="background:rgba(0,0,0,.25);padding:12px 18px;color:#fff;font-size:10px;text-align:right;display:flex;flex-direction:column;justify-content:center;gap:3px">
          <div><b>REF:</b> ${resultadoActual.referencia}</div>
          <div><b>FECHA:</b> ${resultadoActual.fecha_revision}</div>
          <div><b>ID:</b> ${resultadoActual.id}</div>
        </div>
      </div>

      <!-- SEMÁFORO -->
      <div style="display:flex;align-items:center;gap:14px;padding:12px 18px;border-radius:8px;border-left:6px solid ${color};background:${color}18;margin-bottom:16px">
        <div style="width:16px;height:16px;border-radius:50%;background:${color};flex-shrink:0"></div>
        <div>
          <div style="font-size:15px;font-weight:700;color:${color}">${semNombres[resultadoActual.semaforo] || ''}</div>
          <div style="font-size:10px;color:#555;margin-top:2px">${resultadoActual.recomendacion}</div>
        </div>
      </div>

      <!-- CONTADORES -->
      <div style="display:flex;gap:10px;margin-bottom:18px">
        <div style="flex:1;text-align:center;padding:10px;border-radius:8px;border-top:3px solid #CC1F2F;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)">
          <div style="font-size:22px;font-weight:700;color:#CC1F2F">${resultadoActual.total_criticos}</div>
          <div style="font-size:9px;color:#888;text-transform:uppercase">Críticos</div>
        </div>
        <div style="flex:1;text-align:center;padding:10px;border-radius:8px;border-top:3px solid #e67e22;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)">
          <div style="font-size:22px;font-weight:700;color:#e67e22">${resultadoActual.total_altos}</div>
          <div style="font-size:9px;color:#888;text-transform:uppercase">Altos</div>
        </div>
        <div style="flex:1;text-align:center;padding:10px;border-radius:8px;border-top:3px solid #c49b0a;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)">
          <div style="font-size:22px;font-weight:700;color:#c49b0a">${resultadoActual.total_medios}</div>
          <div style="font-size:9px;color:#888;text-transform:uppercase">Medios</div>
        </div>
        <div style="flex:1;text-align:center;padding:10px;border-radius:8px;border-top:3px solid #27ae60;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)">
          <div style="font-size:22px;font-weight:700;color:#27ae60">${resultadoActual.total_bajos}</div>
          <div style="font-size:9px;color:#888;text-transform:uppercase">Bajos</div>
        </div>
      </div>

      <!-- TABLA -->
      <div style="font-size:12px;font-weight:600;color:#1B2B6B;padding:8px 0;border-bottom:2px solid #1B2B6B;margin-bottom:8px">Tabla de Hallazgos</div>
      <table style="width:100%;border-collapse:collapse;font-size:10px">
        <thead>
          <tr style="background:#1B2B6B">
            <th style="color:#fff;padding:7px 8px;text-align:left;font-size:9px">Campo</th>
            <th style="color:#fff;padding:7px 8px;text-align:left;font-size:9px">Valor Pedimento</th>
            <th style="color:#fff;padding:7px 8px;text-align:left;font-size:9px">Valor Documento</th>
            <th style="color:#fff;padding:7px 8px;text-align:left;font-size:9px">Fuente</th>
            <th style="color:#fff;padding:7px 8px;text-align:left;font-size:9px">Fundamento</th>
            <th style="color:#fff;padding:7px 8px;text-align:center;font-size:9px">Riesgo</th>
            <th style="color:#fff;padding:7px 8px;text-align:left;font-size:9px">Acción</th>
          </tr>
        </thead>
        <tbody>${filas}</tbody>
      </table>

      <!-- FOOTER -->
      <div style="text-align:center;color:#aaa;font-size:9px;margin-top:20px;padding-top:10px;border-top:1px solid #e0e4ef">
        Generado por <strong style="color:#1B2B6B">CIE GLOSA</strong> — Sistema de Glosa Preventiva Aduanal
      </div>
    </div>`;

  // Cargar html2pdf desde CDN y generar PDF real
  if (!window.html2pdf) {
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js';
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  const elemento = document.createElement('div');
  elemento.innerHTML = contenido;
  document.body.appendChild(elemento);

  await html2pdf().set({
    margin: [10, 10, 10, 10],
    filename: `Glosa_${resultadoActual.referencia}_${resultadoActual.id}.pdf`,
    image: { type: 'jpeg', quality: 0.95 },
    html2canvas: { scale: 2, useCORS: true, logging: false },
    jsPDF: { unit: 'mm', format: 'a4', orientation: 'landscape' }
  }).from(elemento).save();

  document.body.removeChild(elemento);
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
