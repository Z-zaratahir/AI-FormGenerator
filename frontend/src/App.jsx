import { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import FormField from './components/FormField';
import AddFieldButton from './components/AddFieldButton';

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

// We've moved the FormField component to its own file
// Now using the imported FormField component instead


// --- Main App Component ---
function App() {
  const [prompt, setPrompt] = useState("make a registration form");
  const [formData, setFormData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionStatus, setSubmissionStatus] = useState({ message: '', errors: null, success: false });

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

  const handleGenerate = async () => {
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