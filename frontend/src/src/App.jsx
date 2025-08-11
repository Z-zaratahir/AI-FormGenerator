import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import './App.css';
import Home from './Home';
import FormField from './components/FormField';
import AddFieldButton from './components/AddFieldButton';
import logoForm from './assets/logoForm 1.svg';

function formatValidationRules(validation) {
  if (!validation || Object.keys(validation).length === 0) {
    return null;
  }
  const rules = Object.entries(validation)
    .map(([key, value]) => {
      return value === true ? key : `${key}: ${value}`;
    })
    .join(', ');
  return ` (Validation: ${rules})`;
}

function FormBuilder() {
  const [searchParams] = useSearchParams();
  const urlPrompt = searchParams.get('prompt');
  
  const [prompt, setPrompt] = useState(urlPrompt || "make a registration form");
  const [formData, setFormData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('prompt');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionStatus, setSubmissionStatus] = useState({ message: '', errors: null, success: false });
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  console.log('FormBuilder mounted, urlPrompt:', urlPrompt);

  const handleGenerate = async () => {
    console.log('handleGenerate called with prompt:', prompt);
    if (!prompt) { setError("Please enter a prompt."); return; }
    setError('');
    setFormData(null);
    setSubmissionStatus({ message: '', errors: null, success: false }); 
    setLoading(true);

    try {
      const res = await axios.post('http://127.0.0.1:5000/process', { prompt });
      
      // Add some default metadata for form fields
      const fieldsWithMeta = res.data.fields.map(field => ({
        ...field,
        source: 'AI Detection',
        confidence: 0.95
      }));
      
      setFormData({
        ...res.data,
        fields: fieldsWithMeta
      });
    } catch (err) {
      const errorMessage = err.response?.data?.message || err.response?.data?.error || 'Failed to connect to the backend.';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // Auto-generate when coming from home page with prompt
  useEffect(() => {
    if (urlPrompt && urlPrompt.trim()) {
      console.log('Auto-generating form for prompt:', urlPrompt);
      handleGenerate();
    }
  }, [urlPrompt]);

  // Listen for popup close event to clear validation errors
  useEffect(() => {
    const handleClearValidationErrors = () => {
      setSubmissionStatus(prev => ({
        ...prev,
        errors: null,
        message: ''
      }));
    };

    window.addEventListener('clearValidationErrors', handleClearValidationErrors);
    
    return () => {
      window.removeEventListener('clearValidationErrors', handleClearValidationErrors);
    };
  }, []);
  
  // Handle adding a new field
  const handleAddField = (newField) => {
    if (!formData) return;
    setFormData({
      ...formData,
      fields: [...formData.fields, {
        ...newField,
        source: 'User Added',
        confidence: 1.0
      }]
    });
  };
  
  // Handle updating an existing field
  const handleUpdateField = (updatedField) => {
    if (!formData) return;
    const updatedFields = formData.fields.map(field => 
      field.id === updatedField.id ? {
        ...updatedField,
        source: field.source,
        confidence: field.confidence
      } : field
    );
    
    setFormData({
      ...formData,
      fields: updatedFields
    });
  };
  
  // Handle deleting a field
  const handleDeleteField = (fieldIdToDelete) => {
    if (!formData) return;
    const updatedFields = formData.fields.filter(
      (field) => field.id !== fieldIdToDelete
    );
    setFormData({
      ...formData,
      fields: updatedFields,
    });
  };
  
  const handleSubmit = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    setSubmissionStatus({ message: '', errors: null, success: false });

    const form = event.target;
    const values = Object.fromEntries(new FormData(form).entries());
    
    const payload = {
      values,
      schema: formData.fields,
    };

    try {
      const res = await axios.post('http://127.0.0.1:5000/submit', payload);
      setSubmissionStatus({ message: res.data.message, success: true });
      form.reset();
    } catch (err) {
      const { message = 'Submission failed. Please check the errors below.', errors = {} } = err.response?.data || {};
      setSubmissionStatus({ message, errors, success: false });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="app-container">
      {/* Top Header Bar */}
      <header className="top-header">
        <div className="header-left">
          <img src={logoForm} alt="FORMAVERSE Logo" className="navbar-logo-svg" />
        </div>
        <div className="header-right">
          <button className="action-btn discard-btn" onClick={() => {}} title="Discard">
            {/* Trash SVG */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
            Discard
          </button>
          <button className="action-btn save-btn" onClick={() => {}} title="Save">
            {/* Floppy disk SVG */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            Save
          </button>
          <button className="action-btn publish-btn" onClick={() => {}} title="Publish">
            {/* Rocket SVG */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 16s.5-2 2-4c2-2 6-6 10-6s8 4 8 8-4 8-8 8-8-4-8-8z"/><circle cx="12" cy="12" r="3"/></svg>
            Publish
          </button>
        </div>
      </header>

      <div className="main-content">
        {/* Left Sidebar */}
        <aside className="left-sidebar">
          <nav className="sidebar-nav">
            <button 
              className={`nav-item ${activeTab === 'prompt' ? 'active' : ''}`}
              onClick={() => setActiveTab('prompt')}
            >
              <div className="nav-icon">🤖</div>
              <span>Prompt</span>
            </button>
            
            <button 
              className={`nav-item ${activeTab === 'template' ? 'active' : ''}`}
              onClick={() => setActiveTab('template')}
            >
              <div className="nav-icon">📄</div>
              <span>Template</span>
            </button>
            
            <button 
              className={`nav-item ${activeTab === 'theme' ? 'active' : ''}`}
              onClick={() => setActiveTab('theme')}
            >
              <div className="nav-icon">🎨</div>
              <span>Theme</span>
            </button>
            
            <button 
              className={`nav-item ${activeTab === 'share' ? 'active' : ''}`}
              onClick={() => setActiveTab('share')}
            >
              <div className="nav-icon">📤</div>
              <span>Share</span>
            </button>
          </nav>
          
          <div className="sidebar-bottom">
            <button className="help-btn">
              <div className="help-icon">?</div>
            </button>
          </div>
        </aside>

        {/* Main Form Area */}
        <main className="form-main">
          <div className="form-header">
            <div className="form-nav">
              <button className="back-btn">←</button>
              <span className="form-title">Form 1</span>
            </div>
            <div className="form-meta">
              <span className="made-by">Made by FORMAVERSE</span>
            </div>
            <div className="form-actions">
              <span className="step-indicator">Step {currentPage} of {totalPages}</span>
              <button className="edit-btn">✏️</button>
              <button className="preview-btn">👁️</button>
            </div>
          </div>

          <div className="form-content">
            {/* Always visible prompt section */}
            <div className="prompt-section">
              <h2>✨ Create Your Perfect Form</h2>
              <p>Describe what kind of form you need and watch the magic happen</p>
              
              <div className="prompt-input-container">
                <textarea
                  placeholder="Enter your Prompt here"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="prompt-textarea"
                  maxLength="500"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleGenerate();
                    }
                  }}
                />
                <button 
                  onClick={handleGenerate} 
                  disabled={loading || !prompt.trim()} 
                  className="prompt-send-btn"
                  title="Generate Form"
                >
                  {loading ? (
                    <span className="send-icon">⏳</span>
                  ) : (
                    <span className="send-icon">➤</span>
                  )}
                </button>
              </div>
            </div>

            {error && <div className="error-message">❌ {error}</div>}

            {submissionStatus.message && (
              <div className={submissionStatus.success ? "success-message" : "error-message"}>
                {submissionStatus.success ? '✅' : '❌'} {submissionStatus.message}
              </div>
            )}

            {formData && formData.fields.length > 0 && (
              <div className="form-preview">
                <div className="form-header-section">
                  <h1 className="form-title-main">Form Preview</h1>
                  <p className="form-description">
                    Review and edit your generated form
                  </p>
                </div>
                
                <form onSubmit={handleSubmit} className="generated-form">
                  {formData.fields.map((field, idx) => {
                    const fieldError = submissionStatus.errors?.[field.id];
                    return (
                      <div key={`${field.id || field.label}-${idx}`} className="field-wrapper">
                        <FormField 
                          field={field} 
                          index={idx}
                          onUpdate={handleUpdateField}
                          onDelete={handleDeleteField}
                        />
                        {fieldError && <div className="field-error">{fieldError}</div>}
                      </div>
                    )
                  })}
                  
                  {/* Add Field Button */}
                  <AddFieldButton onAddField={handleAddField} />
                  
                  <div className="form-actions-bottom">
                    <button type="button" className="cancel-btn">Cancel</button>
                    <button type="submit" className="next-btn" disabled={isSubmitting}>
                      {isSubmitting ? 'Submitting...' : 'Submit'}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* Show Add Field Button when no fields exist */}
            {formData && formData.fields.length === 0 && (
              <div className="form-preview">
                <div className="form-header-section">
                  <h1 className="form-title-main">Create Your Form</h1>
                  <p className="form-description">
                    Start building your form by adding questions and fields.
                  </p>
                </div>
                
                <div className="generated-form">
                  {/* Add Field Button for empty form */}
                  <AddFieldButton onAddField={handleAddField} />
                </div>
              </div>
            )}
          </div>

          {/* Fixed Feedback Section */}
          <div className="feedback-section">
            <p>Kindly Give us Feedback of the form</p>
            <div className="rating-stars">
              <span className="star">⭐</span>
              <span className="star">⭐</span>
              <span className="star">⭐</span>
              <span className="star">⭐</span>
              <span className="star">⭐</span>
            </div>
          </div>
        </main>

        {/* Right Sidebar */}
        <aside className="right-sidebar">
          <div className="sidebar-tabs">
            <button className={`tab-btn ${activeTab === 'pages' ? 'active' : ''}`} onClick={() => setActiveTab('pages')}>
              Pages
            </button>
            <button className={`tab-btn ${activeTab === 'responses' ? 'active' : ''}`} onClick={() => setActiveTab('responses')}>
              Responses
            </button>
          </div>
          
          <div className="sidebar-content">
            {activeTab === 'pages' && (
              <div className="pages-section">
                <div className="page-preview">
                  <div className="page-thumbnail">
                    <div className="thumbnail-content">
                      <h4>Personal Information - Profile Setup</h4>
                      <p>Complete Name *</p>
                      <p>Date of birth *</p>
                      <p>Gender</p>
                    </div>
                  </div>
                  <div className="page-info">
                    <span>Page 1</span>
                    <button className="page-menu">⋯</button>
                  </div>
                </div>
                
                <div className="page-preview">
                  <div className="page-thumbnail">
                    <div className="thumbnail-content">
                      <h4>Page 2</h4>
                    </div>
                  </div>
                  <div className="page-info">
                    <span>Page 2</span>
                    <button className="page-menu">⋯</button>
                  </div>
                </div>
                
                <button className="add-page-btn">
                  <span>+</span>
                  <span>Add More</span>
                </button>
              </div>
            )}
            
            {activeTab === 'responses' && (
              <div className="responses-section">
                <p>No responses yet</p>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/form-builder" element={<FormBuilder />} />
      </Routes>
    </Router>
  );
}

export default App;
