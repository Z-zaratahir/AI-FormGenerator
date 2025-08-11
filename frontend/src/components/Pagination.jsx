
import PropTypes from 'prop-types';
import '../styles/Pagination.css';

function Pagination({ currentPage, totalPages, onPageChange }) {
  const pageNumbers = [];
  
  // Generate page numbers with ellipsis for many pages
  if (totalPages <= 5) {
    // Show all page numbers if 5 or fewer pages
    for (let i = 1; i <= totalPages; i++) {
      pageNumbers.push(i);
    }
  } else {
    // First page
    pageNumbers.push(1);
    
    // Middle pages with ellipsis
    if (currentPage > 3) {
      pageNumbers.push('...');
    }
    
    // Pages around current page
    const startPage = Math.max(2, currentPage - 1);
    const endPage = Math.min(totalPages - 1, currentPage + 1);
    
    for (let i = startPage; i <= endPage; i++) {
      pageNumbers.push(i);
    }
    
    // Ellipsis before last page
    if (currentPage < totalPages - 2) {
      pageNumbers.push('...');
    }
    
    // Last page
    pageNumbers.push(totalPages);
  }
  
  return (
    <div className="pagination">
      <button 
        className="pagination-button" 
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
      >
        &laquo; Prev
      </button>
      
      <div className="page-numbers">
        {pageNumbers.map((pageNumber, index) => (
          pageNumber === '...' ? 
            <span key={`ellipsis-${index}`} className="ellipsis">...</span> :
            <button
              key={pageNumber}
              className={`page-number ${pageNumber === currentPage ? 'active' : ''}`}
              onClick={() => onPageChange(pageNumber)}
            >
              {pageNumber}
            </button>
        ))}
      </div>
      
      <button 
        className="pagination-button" 
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
      >
        Next &raquo;
      </button>
    </div>
  );
}

Pagination.propTypes = {
  currentPage: PropTypes.number.isRequired,
  totalPages: PropTypes.number.isRequired,
  onPageChange: PropTypes.func.isRequired
};

export default Pagination;
