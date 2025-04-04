from flask import Flask, render_template, request, jsonify, url_for
import os
from langsmith import traceable
import json
from agent_app import build_graph, SummaryStateInput

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/research', methods=['POST'])
def research():
    try:
        # Get the research topic from the form
        data = request.get_json()
        research_topic = data.get('research_topic', '')
        
        if not research_topic:
            return jsonify({'error': 'Research topic is required'}), 400
        
        # Build the graph
        graph = build_graph()
        
        # Create input state
        research_input = SummaryStateInput(research_topic=research_topic)
        
        # Run the graph
        result = graph.invoke(research_input)
        
        # Return the summary as JSON
        return jsonify({
            'summary': result['running_summary'],
            'success': True
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

if __name__ == '__main__':
    # Create templates and static directories if they don't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    app.run(debug=True, port=5000)