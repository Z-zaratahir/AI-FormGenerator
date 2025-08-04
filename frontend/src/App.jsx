import { useState } from 'react';
import axios from 'axios';
import './App.css';

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

// --- Reusable FormField Component (This remains UNCHANGED from your original) ---
function FormField({ field, index }) {

  const isRequired = field.validation?.required || false;
  
  const inputId = `${field.id || 'field'}-${index}`;

  const inputProps = {
    id: inputId,
    name: field.id,
    style: { width: '100%', boxSizing: 'border-box', padding: '8px', marginTop: '5px', borderRadius: '4px', border: '1px solid #ccc' },
    required: isRequired,
    placeholder: field.placeholder || '',
  };

  if (field.type === 'number' || field.type === 'range' || field.type === 'rating') {
    if (field.validation?.min !== undefined) inputProps.min = field.validation.min;
    if (field.validation?.max !== undefined) inputProps.max = field.validation.max;
  }

  const renderInput = () => {
    switch (field.type) {
      case 'textarea':
        return <textarea {...inputProps} rows="5" />;
      case 'select':
        return (
          <select {...inputProps}>
            <option value="">-- Please choose an option --</option>
            {field.options && field.options.map((option, idx) => (
              <option key={idx} value={option.toLowerCase().replace(/\s/g, '-')}>{option}</option>
            ))}
          </select>
        );
      case 'radio':
        return (
          <div style={{ marginTop: '8px', display: 'flex', gap: '20px' }}>
            <label>
              <input type="radio" name={inputProps.name} value="yes" style={{width: 'auto', marginRight: '5px'}} />
              Yes
            </label>
            <label>
              <input type="radio" name={inputProps.name} value="no" style={{width: 'auto', marginRight: '5px'}} />
              No
            </label>
          </div>
        );
      case 'file':
        return <input type="file" {...inputProps} style={{...inputProps.style, padding: '4px'}} />;
      case 'checkbox':
        return (
          <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center' }}>
            <input type="checkbox" {...inputProps} style={{width: 'auto', marginRight: '10px'}} />
          </div>
        );
      case 'rating':
        console.log('Rating field:', field.id, 'validation:', field.validation);
        return (
          <input
            type="number"
            {...inputProps}
            min={field.validation?.min ?? 1}
            max={field.validation?.max ?? 5}
            defaultValue={field.validation?.min ?? 1}
            step={1}
          />
        );
      default:
        return <input type={field.type} {...inputProps} />;
    }
  };

  return (
    <div 
      className="form-field-container"
      style={{ backgroundColor: field.confidence > 0.9 ? '#fff' : '#fffbe6' }}
    >
      {field.type !== 'checkbox' ? (
        <label htmlFor={inputId} style={{ fontWeight: 'bold' }}>
          {field.label}
          {isRequired && <span style={{ color: 'red', marginLeft: '4px' }}>*</span>}
        </label>
      ) : (
        <label htmlFor={inputId} style={{ fontWeight: 'bold', display: 'flex', alignItems: 'center' }}>
            {renderInput()}
            <span>{field.label}</span>
            {isRequired && <span style={{ color: 'red', marginLeft: '4px' }}>*</span>}
        </label>
      )}
      
      {field.type !== 'checkbox' && renderInput()}
      
      <div className="debug-info">
        <em>
          Detected via: {field.source} (Confidence: {Math.round(field.confidence * 100)}%)
          {formatValidationRules(field.validation)}
        </em>
      </div>
    </div>
  );
}


// --- Main App Component ---
function App() {
  const [prompt, setPrompt] = useState("make a registration form");
  const [formData, setFormData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionStatus, setSubmissionStatus] = useState({ message: '', errors: null, success: false });

  const handleGenerate = async () => {
    if (!prompt) { setError("Please enter a prompt."); return; }
    setError('');
    setFormData(null);
    setSubmissionStatus({ message: '', errors: null, success: false }); 
    setLoading(true);

    try {
      const res = await axios.post('http://127.0.0.1:5000/process', { prompt });
      setFormData(res.data);
    } catch (err) {
      const errorMessage = err.response?.data?.message || err.response?.data?.error || 'Failed to connect to the backend.';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };
  
  // This function handles removing a field from the state
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
      <header className="app-header">
        <h1>AI Form Generator</h1>
        <p>Describe the form you want to build. Try being specific!</p>
      </header>

      <div className="prompt-section">
        <textarea
          rows="5"
          placeholder="e.g., A contact form with a required name, email, and a comment section. Also add a rating from 1 to 5."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <button onClick={handleGenerate} disabled={loading}>
          {loading ? 'Generating...' : 'Generate Form'}
        </button>
      </div>

      {error && <div className="error-message">❌ {error}</div>}

      {submissionStatus.message && (
        <div className={submissionStatus.success ? "success-message" : "error-message"}>
          {submissionStatus.success ? '✅' : '❌'} {submissionStatus.message}
        </div>
      )}


       {formData && formData.fields.length > 0 && (
        <div className="form-preview">
          <h2>{formData.title}</h2>
          <p className="debug-info"><em>Template matched: {formData.template}</em></p>
          <form onSubmit={handleSubmit}>
            {formData.fields.map((field, idx) => {
              const fieldError = submissionStatus.errors?.[field.id];
              return (
                // This wrapper is the key. It holds both the field and its delete button.
                <div key={`${field.id || field.label}-${idx}`} className="field-wrapper">
                  <FormField field={field} index={idx} />
                  <button 
                    type="button" 
                    onClick={() => handleDeleteField(field.id)} 
                    className="delete-field-btn"
                    aria-label={`Delete ${field.label} field`}
                  >
                    ×
                  </button>
                  {fieldError && <div className="field-error">{fieldError}</div>}
                </div>
              )
            })}
            <button type="submit" className="submit-button" disabled={isSubmitting}>
              {isSubmitting ? 'Submitting...' : 'Submit Form'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default App;