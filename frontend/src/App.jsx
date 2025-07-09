import { useState } from 'react';
import axios from 'axios';
import './App.css'; 

// --- Reusable FormField Component ---
// This component now handles text, number, email, file, textarea, select, radio, and checkbox.
function FormField({ field }) {
  const isConfident = field.confidence > 0.9;

  const inputProps = {
    name: field.label.toLowerCase().replace(/\s/g, '-'),
    style: { width: '100%', boxSizing: 'border-box', padding: '8px', marginTop: '5px', borderRadius: '4px', border: '1px solid #ccc' },
    required: field.required || false,
    placeholder: field.placeholder || '',
  };

  if (field.type === 'number') {
    if (field.min !== undefined) inputProps.min = field.min;
    if (field.max !== undefined) inputProps.max = field.max;
  }

  const renderInput = () => {
    switch (field.type) {
      case 'textarea':
        return <textarea {...inputProps} rows="5" />;
      
      case 'select':
        return (
          <select {...inputProps}>
            <option value="">-- Please choose an option --</option>
            <option value="opt1">Option 1</option>
            <option value="opt2">Option 2</option>
          </select>
        );

      case 'radio': // For Yes/No
        return (
          <div style={{ marginTop: '8px' }}>
            <label style={{ marginRight: '15px' }}>
              <input type="radio" name={inputProps.name} value="yes" /> Yes
            </label>
            <label>
              <input type="radio" name={inputProps.name} value="no" /> No
            </label>
          </div>
        );

      case 'checkbox':
        // For a real app, options would come from the prompt
        return (
          <div style={{ marginTop: '8px' }}>
            <label>
              <input type="checkbox" name={`${inputProps.name}-1`} /> Option A
            </label>
          </div>
        );
        
      default:
        return <input type={field.type} {...inputProps} />;
    }
  };

  return (
    <div 
      className="form-field-container"
      style={{ backgroundColor: isConfident ? '#fff' : '#fffbe6' }}
    >
      <label style={{ fontWeight: 'bold' }}>
        {field.label}
        {field.required && <span style={{ color: 'red', marginLeft: '4px' }}>*</span>}
      </label>
      
      {renderInput()}
      
      <div className="debug-info">
        <em>
          Detected via: {field.source} (Confidence: {Math.round(field.confidence * 100)}%)
          {field.min !== undefined && ` (Min: ${field.min})`}
          {field.max !== undefined && ` (Max: ${field.max})`}
        </em>
      </div>
    </div>
  );
}


// --- Main App Component ---
function App() {
  const [prompt, setPrompt] = useState('Create a form for emial, first name and last name, a required dropdown for country selection, and a rating from 1 to 7.');
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
      const errorMessage = err.response?.data?.error || 'Failed to connect to the backend.';
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
          <form onSubmit={(e) => e.preventDefault()}>
            {formData.fields.map((field, idx) => (
              <FormField key={`${field.label}-${idx}`} field={field} />
            ))}
            <button type="submit" className="submit-button">Submit Form</button>
          </form>
        </div>
      )}
    </div>
  );
}

export default App;