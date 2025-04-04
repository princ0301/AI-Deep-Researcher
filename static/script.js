document.addEventListener('DOMContentLoaded', function() {
    const researchForm = document.getElementById('researchForm');
    const resultsSection = document.getElementById('results-section');
    const loadingElement = document.getElementById('loading');
    const resultsContainer = document.getElementById('results-container');
    const summaryContent = document.getElementById('summary-content');
    const sourcesContent = document.getElementById('sources-content');
    const copyBtn = document.getElementById('copy-btn');

    // Hide results section initially
    resultsSection.style.display = 'none';

    researchForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const researchTopic = document.getElementById('research-topic').value.trim();
        
        if (!researchTopic) {
            alert('Please enter a research topic');
            return;
        }
        
        // Show results section and loading spinner
        resultsSection.style.display = 'block';
        loadingElement.style.display = 'flex';
        resultsContainer.style.display = 'none';
        
        // Scroll to results section
        resultsSection.scrollIntoView({ behavior: 'smooth' });
        
        try {
            const response = await fetch('/research', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ research_topic: researchTopic }),
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Error generating research');
            }
            
            // Process and display the results
            displayResults(data.summary);
            
        } catch (error) {
            console.error('Error:', error);
            summaryContent.innerHTML = `
                <div class="error-message">
                    <p><strong>Error:</strong> ${error.message}</p>
                    <p>Please try again with a different topic or check your connection.</p>
                </div>
            `;
            resultsContainer.style.display = 'block';
        } finally {
            loadingElement.style.display = 'none';
        }
    });
    
    function displayResults(summary) {
        // Split the summary and sources
        const parts = summary.split('### Sources:');
        const summaryText = parts[0].replace('## Summary', '').trim();
        
        // Format the summary with proper paragraphs
        summaryContent.innerHTML = summaryText.split('\n\n')
            .filter(para => para.trim() !== '')
            .map(para => `<p>${para}</p>`)
            .join('');
        
        // Format the sources if available
        if (parts.length > 1) {
            const sourcesText = parts[1].trim();
            sourcesContent.innerHTML = `
                <h3>Sources:</h3>
                <ul>
                    ${sourcesText.split('\n')
                        .filter(source => source.trim() !== '')
                        .map(source => {
                            // Extract URL if possible
                            const urlMatch = source.match(/(https?:\/\/[^\s]+)/);
                            const url = urlMatch ? urlMatch[0] : '';
                            
                            if (url) {
                                return `<li><a href="${url}" target="_blank">${source.replace('* ', '')}</a></li>`;
                            } else {
                                return `<li>${source.replace('* ', '')}</li>`;
                            }
                        })
                        .join('')}
                </ul>
            `;
        } else {
            sourcesContent.innerHTML = '';
        }
        
        // Show results container
        resultsContainer.style.display = 'block';
    }
    
    // Copy to clipboard functionality
    copyBtn.addEventListener('click', function() {
        const summaryText = summaryContent.innerText;
        const sourcesText = sourcesContent.innerText;
        
        const textToCopy = `${summaryText}\n\n${sourcesText}`;
        
        navigator.clipboard.writeText(textToCopy).then(function() {
            const originalText = copyBtn.innerHTML;
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            copyBtn.style.backgroundColor = 'var(--success-color)';
            
            setTimeout(function() {
                copyBtn.innerHTML = originalText;
                copyBtn.style.backgroundColor = 'var(--accent-color)';
            }, 2000);
        }, function(err) {
            console.error('Could not copy text: ', err);
            alert('Failed to copy to clipboard');
        });
    });
});