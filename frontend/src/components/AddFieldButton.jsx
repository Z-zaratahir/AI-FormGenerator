import { useState } from 'react';
import PropTypes from 'prop-types';
import FieldTypeSelector from './FieldTypeSelector';
import '../styles/AddFieldButton.css';

/**
 * AddFieldButton Component
 * 
 * A button that opens the field type selector modal to add a new field
 * 
 * @param {function} onAddField - Function to call with the new field data
 */
function AddFieldButton({ onAddField }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleOpenModal = () => {
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
  };

  const handleSelectFieldType = (fieldType) => {
    // Generate a default field based on the selected type
    const newField = {
      id: `${fieldType.toUpperCase()}_${Date.now()}`,
      label: getDefaultLabelForType(fieldType),
      type: fieldType,
      validation: {},
      options: fieldType === 'select' || fieldType === 'radio' ? ['Option 1', 'Option 2'] : []
    };
    
    // Call the parent component's handler with the new field
    onAddField(newField);
  };

  const getDefaultLabelForType = (type) => {
    const labelMap = {
      text: 'Text Field',
      textarea: 'Long Text Field',
      email: 'Email Address',
      number: 'Number Field',
      select: 'Dropdown Selection',
      checkbox: 'Checkbox Field',
      radio: 'Radio Selection',
      date: 'Date Field',
      phone_number: 'Phone Number',
      file: 'File Upload',
      rating: 'Rating'
    };
    
    return labelMap[type] || 'New Field';
  };

  return (
    <>
      <button className="add-field-button" onClick={handleOpenModal}>
        <span className="add-icon">+</span> Add a question
      </button>
      
      <FieldTypeSelector 
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onSelectFieldType={handleSelectFieldType}
        mode="add"
      />
    </>
  );
}

AddFieldButton.propTypes = {
  onAddField: PropTypes.func.isRequired
};

export default AddFieldButton;
