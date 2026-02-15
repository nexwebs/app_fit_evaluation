import { useState, useEffect } from 'react';
import ChatWidget from '../components/ChatWidget';
import './LandingPage.css';

const API_URL = import.meta.env.PUBLIC_API_URL ?? 'http://localhost:8000';

interface Position {
  id: string;
  title: string;
  description: string;
  salary: string;
  currency: string;
  slots_available: number;
  requirements: {
    skills: string[];
    availability: string;
    experience_years: number;
  };
  is_active: boolean;
  created_at: string;
}

export default function LandingPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/evaluations/positions`)
      .then(res => res.json())
      .then(data => {
        setPositions(data.filter((p: Position) => p.is_active));
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching positions:', err);
        setLoading(false);
      });
  }, []);

  const formatSalary = (salary: string, currency: string) => {
    const amount = parseFloat(salary);
    return new Intl.NumberFormat('es-PE', {
      style: 'currency',
      currency: currency,
      minimumFractionDigits: 0,
    }).format(amount);
  };

  const getAvailabilityLabel = (availability: string) => {
    const labels: Record<string, string> = {
      full_time: 'Tiempo Completo',
      part_time: 'Medio Tiempo',
      freelance: 'Freelance',
      internship: 'Pasantía',
    };
    return labels[availability] || availability;
  };

  return (
    <div className="landing-page">
      <header className="header">
        <div className="container header-content">
          <div className="logo">
            <img src="/favicon.svg" alt="TalentoHR" width="32" height="32" />
            <span>TalentoHR</span>
          </div>
          
          <button 
            className="mobile-menu-btn"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Menú"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {mobileMenuOpen ? (
                <path d="M18 6L6 18M6 6l12 12"/>
              ) : (
                <path d="M3 12h18M3 6h18M3 18h18"/>
              )}
            </svg>
          </button>

          <nav className={`nav ${mobileMenuOpen ? 'open' : ''}`}>
            <a href="#vacantes" onClick={() => setMobileMenuOpen(false)}>Vacantes</a>
            <a href="#beneficios" onClick={() => setMobileMenuOpen(false)}>Beneficios</a>
            <a href="#proceso" onClick={() => setMobileMenuOpen(false)}>Proceso</a>
            <a href="#contacto" onClick={() => setMobileMenuOpen(false)}>Contacto</a>
          </nav>
        </div>
      </header>

      <section className="hero">
        <div className="hero-bg"></div>
        <div className="container hero-content">
          <div className="hero-text">
            <span className="hero-badge">¡Únete a nuestro equipo!</span>
            <h1>Encuentra tu próximo <span className="highlight">empleo ideal</span></h1>
            <p>
              Somos una empresa líder en gestión de talento humano. 
              Conectamos profesionales talentosos con oportunidades que transforman carreras.
            </p>
            <div className="hero-cta">
              <a href="#vacantes" className="btn btn-primary">Ver Vacantes</a>
              <a href="#proceso" className="btn btn-outline">Cómo funciona</a>
            </div>
            <div className="hero-stats">
              <div className="stat">
                <span className="stat-number">500+</span>
                <span className="stat-label">Candidatos Colocados</span>
              </div>
              <div className="stat">
                <span className="stat-number">98%</span>
                <span className="stat-label">Satisfacción</span>
              </div>
              <div className="stat">
                <span className="stat-number">50+</span>
                <span className="stat-label">Empresas Aliadas</span>
              </div>
            </div>
          </div>
          <div className="hero-visual">
            <div className="hero-card">
              <div className="hero-card-icon floating">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </div>
              <h3>Evaluación Inteligente</h3>
              <p>Proceso de selección moderno y eficiente</p>
              <button 
                className="btn btn-primary btn-sm"
                onClick={() => document.querySelector('.chat-toggle')?.dispatchEvent(new MouseEvent('click'))}
                style={{marginTop: '1rem'}}
              >
                ¡Inicia tu postulación!
              </button>
            </div>
          </div>
        </div>
      </section>

      <section id="vacantes" className="positions-section">
        <div className="container">
          <div className="section-header">
            <h2>Vacantes Disponibles</h2>
            <p>Explora nuestras oportunidades laborales y postula ahora</p>
          </div>

          {loading ? (
            <div className="loading">
              <div className="spinner"></div>
              <p>Cargando vacantes...</p>
            </div>
          ) : positions.length === 0 ? (
            <div className="empty-state">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              <h3>No hay vacantes disponibles</h3>
              <p>¡Vuelve pronto! Estamos constantemente buscando nuevo talento.</p>
            </div>
          ) : (
            <div className="positions-grid">
              {positions.map((position) => (
                <div key={position.id} className="position-card">
                  <div className="position-header">
                    <h3>{position.title}</h3>
                    <span className="position-slots">
                      {position.slots_available} {position.slots_available === 1 ? 'posición' : 'posiciones'}
                    </span>
                  </div>
                  <p className="position-description">{position.description}</p>
                  <div className="position-salary">
                    <img src="/icon-briefcase.svg" alt="salario" width="16" height="16" style={{display: 'inline-block', verticalAlign: 'middle'}} />
                    {formatSalary(position.salary, position.currency)} /mes
                  </div>
                  <div className="position-meta">
                    <span className="meta-item">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                      </svg>
                      {getAvailabilityLabel(position.requirements.availability)}
                    </span>
                    <span className="meta-item">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>
                        <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
                      </svg>
                      {position.requirements.experience_years}+ años exp.
                    </span>
                  </div>
                  <div className="position-skills">
                    {position.requirements.skills.slice(0, 3).map((skill, idx) => (
                      <span key={idx} className="skill-tag">{skill}</span>
                    ))}
                  </div>
                  <button 
                    className="btn btn-primary btn-block"
                    onClick={() => setSelectedPosition(position)}
                  >
                    Postular ahora
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section id="beneficios" className="benefits-section">
        <div className="container">
          <div className="section-header">
            <h2>Beneficios</h2>
            <p>Nos preocupamos por tu bienestar y desarrollo profesional</p>
          </div>
          <div className="benefits-grid">
            <div className="benefit-card">
              <div className="benefit-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
              </div>
              <h3>Salario Competitivo</h3>
              <p>Remuneración acima del mercado según tu experiencia</p>
            </div>
            <div className="benefit-card">
              <div className="benefit-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                </svg>
              </div>
              <h3>Plan de Salud</h3>
              <p>Cobertura médica para ti y tu familia</p>
            </div>
            <div className="benefit-card">
              <div className="benefit-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                  <line x1="16" y1="2" x2="16" y2="6"/>
                  <line x1="8" y1="2" x2="8" y2="6"/>
                  <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
              </div>
              <h3>Horario Flexible</h3>
              <p>Balance entre vida laboral y personal</p>
            </div>
            <div className="benefit-card">
              <div className="benefit-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
              </div>
              <h3>Capacitación</h3>
              <p>Programas de desarrollo profesional continuo</p>
            </div>
            <div className="benefit-card">
              <div className="benefit-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                  <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
              </div>
              <h3>Trabajo Remoto</h3>
              <p>Modalidad híbrida o remoto según el puesto</p>
            </div>
            <div className="benefit-card">
              <div className="benefit-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
                  <line x1="9" y1="9" x2="9.01" y2="9"/>
                  <line x1="15" y1="9" x2="15.01" y2="9"/>
                </svg>
              </div>
              <h3>Cultura Great Place</h3>
              <p>Ambiente de trabajo positivo y colaborativo</p>
            </div>
          </div>
        </div>
      </section>

      <section id="proceso" className="process-section">
        <div className="container">
          <div className="section-header">
            <h2>Nuestro Proceso de Selección</h2>
            <p>Un proceso transparente y eficiente para encontrar el mejor talento</p>
          </div>
          <div className="process-steps">
            <div className="process-step">
              <div className="step-number">1</div>
              <h3>Postulación</h3>
              <p>Completa tu perfil y responde algunas preguntas iniciales</p>
            </div>
            <div className="process-step">
              <div className="step-number">2</div>
              <h3>Evaluación</h3>
              <p>Realiza nuestras pruebas de competencias y habilidades</p>
            </div>
            <div className="process-step">
              <div className="step-number">3</div>
              <h3>Entrevista</h3>
              <p>Conversamos contigo para conocerte mejor</p>
            </div>
            <div className="process-step">
              <div className="step-number">4</div>
              <h3>¡Empieza!</h3>
              <p>Recibe tu oferta y únete a nuestro equipo</p>
            </div>
          </div>
        </div>
      </section>

      <section id="contacto" className="contact-section">
        <div className="container">
          <div className="contact-content">
            <h2>¿Tienes preguntas?</h2>
            <p>Nuestro equipo de RRHH está disponible para ayudarte</p>
            <div className="contact-info">
              <a href="mailto:rrhh@talenthr.com" className="contact-item">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                  <polyline points="22,6 12,13 2,6"/>
                </svg>
                rrhh@talenthr.com
              </a>
              <a href="tel:+51999999999" className="contact-item">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                </svg>
                +51 999 999 999
              </a>
            </div>
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="container">
          <div className="footer-content">
            <div className="footer-logo">
              <img src="/favicon.svg" alt="TalentoHR" width="24" height="24" />
              <span>TalentoHR</span>
            </div>
            <p className="footer-text">© 2026 TalentoHR. Todos los derechos reservados.</p>
          </div>
        </div>
      </footer>

      <ChatWidget />

      {selectedPosition && (
        <div className="modal-overlay" onClick={() => setSelectedPosition(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setSelectedPosition(null)}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
            <h2>{selectedPosition.title}</h2>
            <p className="modal-description">{selectedPosition.description}</p>
            <div className="modal-details">
              <div className="modal-detail">
                <strong>Salario:</strong> {formatSalary(selectedPosition.salary, selectedPosition.currency)}/mes
              </div>
              <div className="modal-detail">
                <strong>Disponibilidad:</strong> {getAvailabilityLabel(selectedPosition.requirements.availability)}
              </div>
              <div className="modal-detail">
                <strong>Experiencia:</strong> {selectedPosition.requirements.experience_years}+ años
              </div>
            </div>
            <div className="modal-skills">
              <strong>Habilidades requeridas:</strong>
              <div className="skills-list">
                {selectedPosition.requirements.skills.map((skill, idx) => (
                  <span key={idx} className="skill-tag">{skill}</span>
                ))}
              </div>
            </div>
            <p className="modal-note">
              Haz clic en "Iniciar Proceso" para comenzar tu postulación. 
                  Te guiaremos a través de nuestro chat de evaluación.
            </p>
            <button 
              className="btn btn-primary btn-block"
              onClick={() => {
                setSelectedPosition(null);
                document.querySelector('.chat-toggle')?.dispatchEvent(new MouseEvent('click'));
              }}
            >
              Iniciar Proceso
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
