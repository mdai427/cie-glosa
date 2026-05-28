// ===== ESTADO GLOBAL =====
let archivosSeleccionados = new DataTransfer();
let resultadoActual = null;
let todosHallazgos = [];
let _chartSemaforo = null;
let _usuarioActual = null;

// ===== AUTH =====
const TOKEN_KEY = 'glosa_jwt';
const USER_KEY  = 'glosa_user';
const INACTIVIDAD_MS = 8 * 60 * 60 * 1000; // 8 horas
let _timerInactividad = null;

function _getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function _setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  _usuarioActual = user;
  _resetInactividad();
}

function _clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  _usuarioActual = null;
  if (_timerInactividad) clearTimeout(_timerInactividad);
}

function _resetInactividad() {
  if (_timerInactividad) clearTimeout(_timerInactividad);
  _timerInactividad = setTimeout(() => {
    _clearSession();
    mostrarLogin('Tu sesión expiró por inactividad.');
  }, INACTIVIDAD_MS);
}

// Reiniciar timer en cualquier interacción
['click', 'keydown', 'mousemove', 'touchstart'].forEach(ev =>
  document.addEventListener(ev, () => { if (_getToken()) _resetInactividad(); }, { passive: true })
);

async function apiFetch(url, options = {}) {
  const token = _getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    _clearSession();
    mostrarLogin('Sesión expirada. Inicia sesión nuevamente.');
    throw new Error('No autenticado');
  }
  return res;
}

// ===== INICIALIZACIÓN =====
document.addEventListener('DOMContentLoaded', () => {
  const token = _getToken();
  const user  = localStorage.getItem(USER_KEY);
  if (token && user) {
    _usuarioActual = JSON.parse(user);
    mostrarApp();
  } else {
    mostrarLogin();
  }
});

function mostrarLogin(msg = '') {
  document.getElementById('pantalla-login').style.display = 'block';
  document.getElementById('app-principal').style.display  = 'none';
  if (msg) {
    const el = document.getElementById('login-error');
    el.textContent = msg;
    el.style.display = 'block';
  }
  document.getElementById('login-email').value    = '';
  document.getElementById('login-password').value = '';
}

function mostrarApp() {
  document.getElementById('pantalla-login').style.display = 'none';
  document.getElementById('app-principal').style.display  = 'block';
  // Nombre y rol en header
  document.getElementById('header-nombre').textContent = _usuarioActual.nombre || '';
  document.getElementById('header-rol').textContent    = _usuarioActual.rol === 'admin' ? 'Admin' : 'Ejecutivo';
  // Botón admin solo para admins
  const navAdmin = document.getElementById('nav-admin');
  if (navAdmin) navAdmin.style.display = _usuarioActual.rol === 'admin' ? 'inline-flex' : 'none';
  _resetInactividad();
}

async function hacerLogin(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-login');
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Iniciando sesión...';

  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.detail || 'Error al iniciar sesión';
      errEl.style.display = 'block';
      return;
    }
    _setSession(data.token, data.user);
    mostrarApp();
    mostrarSeccion('nueva');
  } catch (err) {
    errEl.textContent = 'Error de conexión. Intenta de nuevo.';
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Iniciar sesión';
  }
}

function toggleVerPass() {
  const inp = document.getElementById('login-password');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

function cerrarSesion() {
  _clearSession();
  mostrarLogin();
}

// ===== ADMIN: USUARIOS =====
async function cargarUsuarios() {
  const div = document.getElementById('tabla-usuarios');
  if (!div) return;
  div.innerHTML = '<p style="color:var(--text3);text-align:center;padding:20px">Cargando...</p>';
  try {
    const res = await apiFetch('/api/admin/usuarios');
    const lista = await res.json();
    if (!lista.length) {
      div.innerHTML = '<p style="color:var(--gris-texto);text-align:center;padding:20px">Sin usuarios registrados.</p>';
      return;
    }
    div.innerHTML = `
      <table class="usuarios-table">
        <thead><tr>
          <th>Nombre</th><th>Correo</th><th>Rol</th><th>Estado</th><th>Creado</th><th>Acción</th>
        </tr></thead>
        <tbody>${lista.map(u => `
          <tr>
            <td><strong>${escHtml(u.nombre)}</strong></td>
            <td>${escHtml(u.email)}</td>
            <td><span class="rol-badge ${u.rol}">${u.rol === 'admin' ? 'Admin' : 'Ejecutivo'}</span></td>
            <td><span class="estado-badge ${u.activo ? 'activo' : 'inactivo'}">${u.activo ? 'Activo' : 'Inactivo'}</span></td>
            <td style="color:var(--gris-texto);font-size:12px">${escHtml(u.created_at || '')}</td>
            <td>
              ${u.id !== _usuarioActual?.id ? `
                <button class="btn-toggle ${u.activo ? 'desactivar' : 'activar'}"
                  onclick="toggleUsuario(${u.id}, ${u.activo})">
                  ${u.activo ? 'Desactivar' : 'Activar'}
                </button>` : '<span style="color:#aaa;font-size:11px">Tú</span>'}
            </td>
          </tr>
        `).join('')}</tbody>
      </table>`;
  } catch (err) {
    div.innerHTML = `<p style="color:var(--critico);padding:20px">Error: ${err.message}</p>`;
  }
}

async function crearUsuario(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-crear-usuario');
  const resEl = document.getElementById('nu-resultado');
  resEl.style.display = 'none';
  btn.disabled = true;
  document.getElementById('btn-crear-texto').textContent = 'Creando...';

  const nombre = document.getElementById('nu-nombre').value.trim();
  const email  = document.getElementById('nu-email').value.trim();
  const rol    = document.getElementById('nu-rol').value;

  try {
    const res = await apiFetch('/api/admin/usuarios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre, email, rol }),
    });
    const data = await res.json();
    if (!res.ok) {
      resEl.className = 'nu-resultado error';
      resEl.textContent = data.detail || 'Error al crear usuario';
      resEl.style.display = 'block';
      return;
    }
    resEl.className = 'nu-resultado ok';
    const correoMsg = data.correo_enviado
      ? `✅ Usuario creado y correo enviado a ${data.email}`
      : `✅ Usuario creado. Correo no enviado — contraseña temporal: ${data.password_temporal}`;
    resEl.textContent = correoMsg;
    resEl.style.display = 'block';
    document.getElementById('form-nuevo-usuario').reset();
    cargarUsuarios();
  } catch (err) {
    resEl.className = 'nu-resultado error';
    resEl.textContent = `Error: ${err.message}`;
    resEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    document.getElementById('btn-crear-texto').textContent = '+ Crear Usuario y Enviar Correo';
  }
}

async function toggleUsuario(id, activoActual) {
  try {
    const res = await apiFetch(`/api/admin/usuarios/${id}/toggle`, { method: 'PATCH' });
    if (res.ok) cargarUsuarios();
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

// ===== NAVEGACIÓN =====
function mostrarSeccion(seccion) {
  ['nueva', 'resultado', 'historial', 'dashboard', 'admin'].forEach(s => {
    const el = document.getElementById(`sec-${s}`);
    if (el) el.style.display = 'none';
  });
  const target = document.getElementById(`sec-${seccion}`);
  if (target) target.style.display = 'block';

  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const navKeyword = { nueva: 'nueva', resultado: 'nueva', historial: 'historial', dashboard: 'dashboard', admin: 'usuarios' };
  const keyword = navKeyword[seccion] || seccion;
  const btn = [...document.querySelectorAll('.nav-btn')].find(b => b.textContent.toLowerCase().includes(keyword));
  if (btn) btn.classList.add('active');

  if (seccion === 'historial') cargarHistorial();
  if (seccion === 'dashboard') cargarDashboard();
  if (seccion === 'admin') cargarUsuarios();
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
    const res = await apiFetch('/api/revision', {
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

  // Campos correctos
  const correctos = data.campos_correctos || [];
  const cardCorrectos = document.getElementById('card-correctos');
  const correctosDiv = document.getElementById('campos-correctos');
  if (correctos.length > 0) {
    cardCorrectos.style.display = '';
    correctosDiv.innerHTML = correctos.map(c =>
      `<div class="correcto-item">✅ ${c}</div>`
    ).join('');
  } else {
    cardCorrectos.style.display = 'none';
  }

  // Reporte experto glosador
  const cardReporte = document.getElementById('card-reporte');
  const reporteContenido = document.getElementById('reporte-contenido');
  if (data.reporte_glosa && data.reporte_glosa.trim()) {
    cardReporte.style.display = '';
    try {
      reporteContenido.innerHTML = markdownAHtml(data.reporte_glosa);
    } catch(e) {
      // Si falla el renderizador, mostrar texto plano
      reporteContenido.innerHTML = '<pre style="white-space:pre-wrap;font-size:13px">' +
        data.reporte_glosa.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') +
        '</pre>';
    }
    // Scroll al reporte
    setTimeout(() => cardReporte.scrollIntoView({behavior:'smooth', block:'start'}), 300);
  } else {
    cardReporte.style.display = 'none';
  }

  // Renderizar tabla y contribuciones
  renderizarTabla(todosHallazgos);
  renderizarContribuciones(todosHallazgos);

  mostrarSeccion('resultado');
  window.scrollTo(0, 0);
}

function toggleReporte() {
  const body = document.getElementById('reporte-body');
  const chevron = document.getElementById('reporte-toggle');
  const oculto = body.style.display === 'none';
  body.style.display = oculto ? '' : 'none';
  chevron.textContent = oculto ? '▼' : '▶';
}

function markdownAHtml(md) {
  // Normalizar saltos de línea
  const lines = md.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  let html = '';
  let i = 0;

  function esc(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  function inline(s) {
    return esc(s)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  while (i < lines.length) {
    const line = lines[i];

    // Línea horizontal
    if (/^---+$/.test(line.trim())) { html += '<hr>'; i++; continue; }

    // Headings
    const h1 = line.match(/^# (.+)/);   if (h1) { html += `<h1>${inline(h1[1])}</h1>`; i++; continue; }
    const h2 = line.match(/^## (.+)/);  if (h2) { html += `<h2>${inline(h2[1])}</h2>`; i++; continue; }
    const h3 = line.match(/^### (.+)/); if (h3) { html += `<h3>${inline(h3[1])}</h3>`; i++; continue; }

    // Tabla Markdown: detectar por primer | al inicio de línea
    if (/^\|/.test(line)) {
      const tableLines = [];
      while (i < lines.length && /^\|/.test(lines[i])) {
        tableLines.push(lines[i]); i++;
      }
      if (tableLines.length >= 2) {
        const headers = tableLines[0].split('|').filter(c => c.trim());
        html += '<table><thead><tr>' +
          headers.map(c => `<th>${inline(c.trim())}</th>`).join('') +
          '</tr></thead><tbody>';
        for (let r = 2; r < tableLines.length; r++) {
          const cells = tableLines[r].split('|').filter(c => c.trim());
          if (cells.length) {
            html += '<tr>' + cells.map(c => `<td>${inline(c.trim())}</td>`).join('') + '</tr>';
          }
        }
        html += '</tbody></table>';
      }
      continue;
    }

    // Lista no ordenada (-, *, •, □, ✅, ⚠️, ❌)
    if (/^[-*•□✅⚠️❌]\s/.test(line) || /^  [-*]\s/.test(line)) {
      html += '<ul>';
      while (i < lines.length && (/^[-*•□✅⚠️❌]\s/.test(lines[i]) || /^  [-*]\s/.test(lines[i]))) {
        const text = lines[i].replace(/^[-*•□✅⚠️❌]\s+/, '').replace(/^  [-*]\s+/, '');
        html += `<li>${inline(text)}</li>`;
        i++;
      }
      html += '</ul>';
      continue;
    }

    // Lista ordenada
    if (/^\d+\.\s/.test(line)) {
      html += '<ol>';
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        const text = lines[i].replace(/^\d+\.\s+/, '');
        html += `<li>${inline(text)}</li>`;
        i++;
      }
      html += '</ol>';
      continue;
    }

    // Línea vacía
    if (line.trim() === '') { i++; continue; }

    // Párrafo normal
    html += `<p>${inline(line)}</p>`;
    i++;
  }

  return html;
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
    const res = await apiFetch('/api/revisiones');
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
    const res = await apiFetch(`/api/revision/${id}`);
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

  const semColors  = { verde: '#1A8A5A', amarillo: '#C47E00', rojo: '#CC1F2F', negro: '#6B4FCC' };
  const semBg      = { verde: '#EAF7F1', amarillo: '#FFF8E6', rojo: '#FDEAEC', negro: '#F0ECFF' };
  const semNombres = { verde: 'PUEDE VALIDAR', amarillo: 'REVISAR ANTES DE VALIDAR', rojo: 'NO VALIDAR', negro: 'RIESGO GRAVE — ESCALAR' };
  const color   = semColors[resultadoActual.semaforo] || '#888';
  const colorBg = semBg[resultadoActual.semaforo]    || '#f9f9f9';

  const logoTag = logoSrc
    ? `<img src="${logoSrc}" style="height:46px;object-fit:contain;display:block">`
    : `<div style="font-size:22px;font-weight:900;color:#CC1F2F;letter-spacing:-1px">CIE</div>`;

  // Filas de la tabla de hallazgos
  let filas = '';
  (resultadoActual.hallazgos || []).forEach((h, i) => {
    const rowBg = i % 2 === 0 ? '#ffffff' : '#f7f9fc';
    const riesgoColor = { Crítico:'#CC1F2F', Alto:'#C47E00', Medio:'#1B6CB0', Bajo:'#1A8A5A' }[h.riesgo] || '#888';
    const riesgoBg    = { Crítico:'#FDEAEC', Alto:'#FFF8E6', Medio:'#E8F2FF', Bajo:'#EAF7F1'  }[h.riesgo] || '#f0f0f0';
    filas += `
      <tr style="background:${rowBg}">
        <td style="font-weight:700;color:#1B2B6B;font-size:10px">${escHtml(h.campo)}</td>
        <td style="font-size:10px">${escHtml(h.valor_pedimento)}</td>
        <td style="font-size:10px">${escHtml(h.valor_documento_fuente)}</td>
        <td style="color:#555;font-size:10px">${escHtml(h.documento_fuente)}</td>
        <td style="font-size:9px;color:#666">${escHtml(h.fundamento_legal)}</td>
        <td style="text-align:center">
          <span style="background:${riesgoBg};color:${riesgoColor};padding:3px 10px;border-radius:12px;font-size:9px;font-weight:700;white-space:nowrap">${escHtml(h.riesgo)}</span>
        </td>
        <td style="font-size:9px;color:#444">${escHtml(h.accion_recomendada)}</td>
      </tr>`;
  });

  const fecha = resultadoActual.fecha_revision || '';

  const html = `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Glosa ${resultadoActual.referencia} — ${resultadoActual.id}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #1a1a2e; background: #fff; }
    /* ---- Print controls (oculto al imprimir) ---- */
    .print-bar {
      position: fixed; top: 0; left: 0; right: 0; z-index: 999;
      background: #1B2B6B; padding: 10px 20px;
      display: flex; align-items: center; gap: 14px;
      border-bottom: 3px solid #CC1F2F;
    }
    .print-bar button {
      background: #CC1F2F; color: #fff; border: none;
      padding: 8px 22px; border-radius: 6px; font-size: 13px;
      font-weight: 700; cursor: pointer; font-family: Arial, sans-serif;
    }
    .print-bar button:hover { background: #a5111f; }
    .print-bar span { color: rgba(255,255,255,0.75); font-size: 12px; }
    .print-content { margin-top: 58px; padding: 20px; max-width: 1100px; margin-left: auto; margin-right: auto; }
    /* ---- Impresión ---- */
    @media print {
      .print-bar { display: none !important; }
      .print-content { margin-top: 0; padding: 0; max-width: none; }
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      @page { size: A4 landscape; margin: 10mm; }
      tr { page-break-inside: avoid; }
    }
    /* ---- Header ---- */
    .rpt-header {
      background: #1B2B6B;
      border-bottom: 5px solid #CC1F2F;
      margin-bottom: 18px;
      border-radius: 6px;
      overflow: hidden;
    }
    .rpt-header table { width: 100%; border-collapse: collapse; }
    .rpt-header td { padding: 0; vertical-align: middle; }
    .hd-logo  { background: #fff; padding: 12px 18px; width: 140px; text-align: center; }
    .hd-title { padding: 12px 20px; color: #fff; }
    .hd-title h1 { font-size: 17px; font-weight: 700; letter-spacing: .4px; margin-bottom: 3px; }
    .hd-title p  { font-size: 10px; opacity: .75; }
    .hd-meta  { background: rgba(0,0,0,.22); padding: 12px 18px; color: #fff; font-size: 10px; text-align: right; white-space: nowrap; }
    .hd-meta div { margin-bottom: 3px; }
    /* ---- Semáforo ---- */
    .sem-band {
      padding: 12px 18px; border-radius: 7px;
      border-left: 6px solid ${color};
      background: ${colorBg};
      margin-bottom: 16px;
      display: table; width: 100%;
    }
    .sem-dot  { display: table-cell; vertical-align: middle; width: 22px; }
    .sem-dot span { display: inline-block; width: 16px; height: 16px; border-radius: 50%; background: ${color}; }
    .sem-text { display: table-cell; vertical-align: middle; padding-left: 12px; }
    .sem-text strong { font-size: 14px; font-weight: 800; color: ${color}; display: block; }
    .sem-text em { font-size: 10px; color: #555; font-style: normal; }
    /* ---- Contadores ---- */
    .contadores { border-collapse: collapse; width: 100%; margin-bottom: 16px; }
    .contadores td { width: 25%; text-align: center; padding: 10px; border-radius: 8px; }
    .cnt-num { font-size: 26px; font-weight: 800; display: block; }
    .cnt-lbl { font-size: 9px; text-transform: uppercase; letter-spacing: .5px; }
    .cnt-c { border-top: 3px solid #CC1F2F; background: #FDEAEC; }
    .cnt-c .cnt-num { color: #CC1F2F; }
    .cnt-a { border-top: 3px solid #C47E00; background: #FFF8E6; }
    .cnt-a .cnt-num { color: #C47E00; }
    .cnt-m { border-top: 3px solid #1B6CB0; background: #E8F2FF; }
    .cnt-m .cnt-num { color: #1B6CB0; }
    .cnt-b { border-top: 3px solid #1A8A5A; background: #EAF7F1; }
    .cnt-b .cnt-num { color: #1A8A5A; }
    /* ---- Tabla ---- */
    .tbl-title { font-size: 12px; font-weight: 700; color: #1B2B6B; padding: 6px 0; border-bottom: 2px solid #1B2B6B; margin-bottom: 8px; }
    .hallazgos-table { width: 100%; border-collapse: collapse; }
    .hallazgos-table th { background: #1B2B6B; color: #fff; padding: 7px 8px; text-align: left; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px; }
    .hallazgos-table td { padding: 7px 8px; border-bottom: 1px solid #e8ecf4; vertical-align: top; line-height: 1.4; }
    /* ---- Footer ---- */
    .rpt-footer { text-align: center; color: #bbb; font-size: 9px; margin-top: 20px; padding-top: 10px; border-top: 1px solid #e0e4ef; }
    /* ---- Dictamen Glosador (Markdown renderizado) ---- */
    .reporte-md h1 { font-size: 14px; font-weight: 800; color: #1B2B6B; margin: 14px 0 6px; }
    .reporte-md h2 { font-size: 13px; font-weight: 700; color: #1B2B6B; margin: 12px 0 5px; border-bottom: 1px solid #dde3f0; padding-bottom: 3px; }
    .reporte-md h3 { font-size: 12px; font-weight: 700; color: #1B2B6B; margin: 10px 0 4px; }
    .reporte-md p  { margin: 4px 0 8px; }
    .reporte-md ul { margin: 4px 0 8px 20px; }
    .reporte-md ol { margin: 4px 0 8px 20px; }
    .reporte-md li { margin-bottom: 3px; }
    .reporte-md strong { font-weight: 700; }
    .reporte-md em { font-style: italic; }
    .reporte-md hr { border: none; border-top: 1px solid #dde3f0; margin: 10px 0; }
    .reporte-md table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 10px; }
    .reporte-md th { background: #1B2B6B; color: #fff; padding: 5px 8px; text-align: left; font-size: 9px; }
    .reporte-md td { padding: 5px 8px; border-bottom: 1px solid #e8ecf4; vertical-align: top; }
    .reporte-md tr:nth-child(even) td { background: #f7f9fc; }
  </style>
</head>
<body>
  <!-- Barra de impresión (solo en pantalla) -->
  <div class="print-bar">
    <button onclick="window.print()">⬇ Guardar como PDF</button>
    <span>En el diálogo de impresión selecciona <b>"Guardar como PDF"</b> como destino — Tamaño: A4 Horizontal</span>
  </div>

  <div class="print-content">
    <!-- HEADER -->
    <div class="rpt-header">
      <table><tr>
        <td class="hd-logo">${logoTag}</td>
        <td class="hd-title">
          <h1>Glosa Preventiva Aduanal</h1>
          <p>CIE Agencia Aduanal — Reporte de Revisión</p>
        </td>
        <td class="hd-meta">
          <div><b>REF:</b> ${escHtml(resultadoActual.referencia)}</div>
          <div><b>FECHA:</b> ${escHtml(fecha)}</div>
          <div><b>ID:</b> ${escHtml(resultadoActual.id)}</div>
        </td>
      </tr></table>
    </div>

    <!-- SEMÁFORO -->
    <div class="sem-band">
      <div class="sem-dot"><span></span></div>
      <div class="sem-text">
        <strong>${semNombres[resultadoActual.semaforo] || ''}</strong>
        <em>${escHtml(resultadoActual.recomendacion)}</em>
      </div>
    </div>

    <!-- CONTADORES -->
    <table class="contadores">
      <tr>
        <td class="cnt-c" style="margin-right:8px">
          <span class="cnt-num">${resultadoActual.total_criticos}</span>
          <span class="cnt-lbl">Críticos</span>
        </td>
        <td width="8"></td>
        <td class="cnt-a">
          <span class="cnt-num">${resultadoActual.total_altos}</span>
          <span class="cnt-lbl">Altos</span>
        </td>
        <td width="8"></td>
        <td class="cnt-m">
          <span class="cnt-num">${resultadoActual.total_medios}</span>
          <span class="cnt-lbl">Medios</span>
        </td>
        <td width="8"></td>
        <td class="cnt-b">
          <span class="cnt-num">${resultadoActual.total_bajos}</span>
          <span class="cnt-lbl">Bajos</span>
        </td>
      </tr>
    </table>

    <!-- TABLA HALLAZGOS -->
    <div class="tbl-title">Tabla de Hallazgos</div>
    <table class="hallazgos-table">
      <thead>
        <tr>
          <th style="width:14%">Campo</th>
          <th style="width:13%">Valor Pedimento</th>
          <th style="width:16%">Valor Documento</th>
          <th style="width:10%">Fuente</th>
          <th style="width:18%">Fundamento Legal</th>
          <th style="width:7%;text-align:center">Riesgo</th>
          <th style="width:22%">Acción Recomendada</th>
        </tr>
      </thead>
      <tbody>${filas}</tbody>
    </table>

    ${resultadoActual.reporte_glosa ? `
    <!-- DICTAMEN GLOSADOR EXPERTO -->
    <div style="margin-top:28px;page-break-before:always">
      <div style="background:#1B2B6B;color:#fff;padding:10px 16px;border-radius:6px 6px 0 0;font-size:12px;font-weight:700;letter-spacing:.3px">
        Dictamen del Glosador Aduanal Experto
      </div>
      <div class="reporte-md" style="border:1px solid #1B2B6B;border-top:none;border-radius:0 0 6px 6px;padding:20px 22px;font-size:11px;line-height:1.7;color:#1a1a2e">
        ${markdownAHtml(resultadoActual.reporte_glosa)}
      </div>
    </div>` : ''}

    <!-- FOOTER -->
    <div class="rpt-footer">
      Generado por <strong style="color:#1B2B6B">CIE GLOSA</strong> — Sistema de Glosa Preventiva Aduanal
    </div>
  </div>

  <script>
    // Imprimir automáticamente al cargar (con pequeño delay para que cargue el logo)
    window.addEventListener('load', function() {
      setTimeout(function() { window.print(); }, 600);
    });
  </script>
</body>
</html>`;

  // Abrir en nueva ventana y disparar impresión
  const w = window.open('', '_blank', 'width=1200,height=800');
  if (!w) {
    alert('El navegador bloqueó la ventana emergente. Permite las ventanas emergentes para este sitio y vuelve a intentarlo.');
    return;
  }
  w.document.write(html);
  w.document.close();
}

// ===== CONTRIBUCIONES =====
function renderizarContribuciones(hallazgos) {
  const card = document.getElementById('card-contribuciones');
  if (!card) return;

  const hallazgoContrib = (hallazgos || []).find(h =>
    h.campo === 'Contribuciones Estimadas de Importación'
  );

  if (!hallazgoContrib) { card.style.display = 'none'; return; }

  card.style.display = 'block';

  // Parsear el string de resumen: "IGI: $X | IVA: $Y | DTA: $Z | TOTAL ESTIMADO: $W"
  const texto = hallazgoContrib.valor_documento_fuente || '';
  const parseVal = (key) => {
    const match = texto.match(new RegExp(key + ':\\s*\\$([\\d,\\.]+)'));
    return match ? '$' + match[1] + ' MXN' : '—';
  };

  document.getElementById('ci-valor').textContent = hallazgoContrib.valor_pedimento || '—';
  document.getElementById('ci-igi').textContent = parseVal('IGI');
  document.getElementById('ci-iva').textContent = parseVal('IVA');
  document.getElementById('ci-dta').textContent = parseVal('DTA');
  document.getElementById('ci-total').textContent = parseVal('TOTAL ESTIMADO');

  // Advertencias TLC
  const tlcHallazgos = (hallazgos || []).filter(h =>
    h.campo.includes('TLC') || h.campo.includes('Preferencial')
  );
  const divAdv = document.getElementById('contrib-advertencias');
  if (divAdv && tlcHallazgos.length > 0) {
    divAdv.innerHTML = tlcHallazgos.map(a =>
      `<div style="font-size:12px;padding:8px 12px;background:rgba(27,43,107,0.06);border-left:3px solid var(--azul-light);border-radius:4px;margin-top:8px;color:var(--azul-dark)">
        🔵 ${escHtml(a.accion_recomendada)}
      </div>`
    ).join('');
  } else if (divAdv) {
    divAdv.innerHTML = '';
  }
}

function toggleContrib() {
  const body = document.getElementById('contrib-body');
  const toggle = document.getElementById('contrib-toggle');
  if (!body) return;
  if (body.style.display === 'none') {
    body.style.display = 'block';
    toggle.textContent = '▲';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▼';
  }
}

// ===== DASHBOARD =====
async function _cargarChartJs() {
  if (window.Chart) return;
  await new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/chart.js';
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

async function cargarDashboard() {
  // Poner indicadores de carga
  ['dash-total', 'dash-verde-pct', 'dash-criticos', 'dash-7dias'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '…';
  });
  const topDiv = document.getElementById('dash-top-campos');
  if (topDiv) topDiv.innerHTML = '<p style="color:var(--gris-texto);text-align:center;padding:20px">Cargando...</p>';

  try {
    const res = await apiFetch('/api/dashboard');
    if (!res.ok) throw new Error(`Error ${res.status}`);
    const d = await res.json();

    const total = d.total_revisiones || 0;
    const sem = d.por_semaforo || {};
    const verde = sem.verde || 0;
    const verdePct = total > 0 ? Math.round((verde / total) * 100) : 0;

    document.getElementById('dash-total').textContent = total;
    document.getElementById('dash-verde-pct').textContent = `${verdePct}%`;
    document.getElementById('dash-criticos').textContent = d.total_criticos ?? 0;
    document.getElementById('dash-7dias').textContent = d.revisiones_ultimos_7_dias || 0;

    await _cargarChartJs();
    _renderizarChartSemaforo(sem);
    _renderizarTopCampos((d.top_campos_hallazgos || []).slice(0, 5));
  } catch (err) {
    ['dash-total', 'dash-verde-pct', 'dash-criticos', 'dash-7dias'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
    if (topDiv) topDiv.innerHTML = `<p class="dash-error">Error al cargar: ${escHtml(err.message)}</p>`;
  }
}

function _renderizarChartSemaforo(sem) {
  const canvas = document.getElementById('chart-semaforo');
  if (!canvas) return;
  if (_chartSemaforo) { _chartSemaforo.destroy(); _chartSemaforo = null; }

  _chartSemaforo = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: ['Verde', 'Amarillo', 'Rojo', 'Negro'],
      datasets: [{
        data: [sem.verde || 0, sem.amarillo || 0, sem.rojo || 0, sem.negro || 0],
        backgroundColor: ['#1A8A5A', '#C47E00', '#CC1F2F', '#6B4FCC'],
        borderRadius: 7,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { stepSize: 1, color: '#8890B5' }, grid: { color: '#D8DCF0' } },
        x: { ticks: { color: '#4A5180', font: { weight: '600' } }, grid: { display: false } }
      }
    }
  });
}

function _renderizarTopCampos(campos) {
  const div = document.getElementById('dash-top-campos');
  if (!div) return;
  if (!campos.length) {
    div.innerHTML = '<p style="color:var(--gris-texto);text-align:center;padding:20px">Sin hallazgos registrados</p>';
    return;
  }
  const maxCount = campos[0].count || 1;
  div.innerHTML = campos.map(c => `
    <div class="top-campo-item">
      <span class="top-campo-name">${escHtml(c.campo)}</span>
      <div class="top-campo-bar-wrap">
        <div class="top-campo-bar" style="width:${Math.round((c.count / maxCount) * 100)}%"></div>
      </div>
      <span class="top-campo-count">${c.count}</span>
    </div>
  `).join('');
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
