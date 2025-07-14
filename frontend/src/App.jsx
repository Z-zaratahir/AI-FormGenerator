import { useState } from 'react';
import axios from 'axios';
import './App.css';

function formatValidationRules(validation) {
  if (!validation || Object.keys(validation).length === 0) {
    return null;
  }
  // Convertng  the validation object into a readable string like "required, minLength: 2"
  const rules = Object.entries(validation)
    .map(([key, value]) => {
      return value === true ? key : `${key}: ${value}`;
    })
    .join(', ');
  return ` (Validation: ${rules})`;
}

// --- Reusable FormField Component ---
function FormField({ field, index }) {

  const isRequired = field.validation?.required || false;
  
  // Creating  a unique ID for accessibility (linking label to input).
  const inputId = `${field.id || 'field'}-${index}`;

  const inputProps = {
    id: inputId,
    name: field.label.toLowerCase().replace(/\s/g, '-'),
    style: { width: '100%', boxSizing: 'border-box', padding: '8px', marginTop: '5px', borderRadius: '4px', border: '1px solid #ccc' },
    required: isRequired,
    placeholder: field.placeholder || '',
  };

  // Add min/max for number types from the validation object
  if (field.type === 'number' || field.type === 'range') {
    if (field.validation?.min !== undefined) inputProps.min = field.validation.min;
    if (field.validation?.max !== undefined) inputProps.max = field.validation.max;
  }

  const renderInput = () => {
    // The switch statement is the single source of truth for rendering.
    switch (field.type) {
      case 'textarea':
        return <textarea {...inputProps} rows="5" />;
      
      // THIS IS THE CORRECTED AND CONSOLIDATED LOGIC
      case 'select':
        return (
          <select {...inputProps}>
            <option value="">-- Please choose an option --</option>
            {/* 
              Check if the 'options' array exists on the field.
              If it does, map over it to create the <option> elements.
            */}
            {field.options && field.options.map((option, idx) => (
              <option key={idx} value={option.toLowerCase().replace(/\s/g, '-')}>
                {option}
              </option>
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
            {/* The label is handled outside already */}
          </div>
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
      {/* For checkboxes, the label should wrap the whole thing or be separate */}
      {field.type !== 'checkbox' ? (
        <label htmlFor={inputId} style={{ fontWeight: 'bold' }}>
          {field.label}
          {isRequired && <span style={{ color: 'red', marginLeft: '4px' }}>*</span>}
        </label>
      ) : (
        // Special rendering for checkbox labels
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
          {/* helper function to show all validation rules */}
          {formatValidationRules(field.validation)}
        </em>
      </div>
    </div>
  );
}


// --- Main App Component ---
function App() {
  const [prompt, setPrompt] = useState("I'm hiring for a new career and I need an application form. It should have fields for a name, the applicant's email, and a phone number, but no address field. Also, add two separate fields for references. The email field must be required.");
  const [formData, setFormData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleGenerate = async () => {
    if (!prompt) { setError("Please enter a prompt."); return; }
    setError('');
    setFormData(null);
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

      {formData && formData.fields.length > 0 && (
        <div className="form-preview">
          <h2>{formData.title}</h2>
          <p className="debug-info"><em>Template matched: {formData.template}</em></p>
          <form onSubmit={(e) => { e.preventDefault(); alert('Form submitted!'); }}>
            {formData.fields.map((field, idx) => (
              // Pass the index for generating a unique key and ID
              <FormField key={`${field.id || field.label}-${idx}`} field={field} index={idx} />
            ))}
            <button type="submit" className="submit-button">Submit Form</button>
          </form>
        </div>
      )}
    </div>
  );
}

export default App;