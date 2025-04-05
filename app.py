from flask import Flask, render_template, request, jsonify, url_for, Response
import os
import json
import threading
import time
from functools import lru_cache
from groq_app import build_graph, SummaryStateInput, Configuration
import datetime

app = Flask(__name__)
 
research_cache = {}
ongoing_research = {}

@app.route('/')
def index():
    return render_template('index.html')

@lru_cache(maxsize=50)
def cached_research(research_topic):
    """Cache research results to avoid redundant processing""" 
    graph = build_graph()
     
    research_input = SummaryStateInput(research_topic=research_topic)
    config = {"configurable": {"max_web_research_loops": 3}}   
     
    result = graph.invoke(research_input, config=config)
    return result

def perform_research(research_id, research_topic):
    """Perform research in a separate thread"""
    try: 
        cache_key = research_topic.lower().strip()
         
        if cache_key in research_cache:
            cache_time, result = research_cache[cache_key] 
            if (datetime.datetime.now() - cache_time).total_seconds() < 86400:   
                ongoing_research[research_id] = {
                    'status': 'complete',
                    'result': result,
                    'progress': 100
                }
                return
         
        ongoing_research[research_id] = {'status': 'running', 'progress': 5}
         
        def update_progress():
            progress = 5
            while research_id in ongoing_research and ongoing_research[research_id]['status'] == 'running' and progress < 90:
                time.sleep(2)
                progress += 5
                if research_id in ongoing_research:
                    ongoing_research[research_id]['progress'] = progress
         
        progress_thread = threading.Thread(target=update_progress)
        progress_thread.daemon = True
        progress_thread.start()
         
        result = cached_research(research_topic)
         
        research_cache[cache_key] = (datetime.datetime.now(), result)
         
        ongoing_research[research_id] = {
            'status': 'complete',
            'result': result,
            'progress': 100
        }
    except Exception as e:
        ongoing_research[research_id] = {
            'status': 'error',
            'error': str(e),
            'progress': 100
        }

@app.route('/research', methods=['POST'])
def research():
    try: 
        data = request.get_json()
        research_topic = data.get('research_topic', '')
        
        if not research_topic:
            return jsonify({'error': 'Research topic is required'}), 400
         
        research_id = f"research_{int(time.time())}_{hash(research_topic) % 10000}"
         
        research_thread = threading.Thread(
            target=perform_research, 
            args=(research_id, research_topic)
        )
        research_thread.daemon = True
        research_thread.start()
         
        return jsonify({
            'research_id': research_id,
            'status': 'started'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

@app.route('/research/status/<research_id>', methods=['GET'])
def research_status(research_id):
    if research_id not in ongoing_research:
        return jsonify({'error': 'Research ID not found'}), 404
    
    research_data = ongoing_research[research_id]
    
    if research_data['status'] == 'complete': 
        result = research_data['result'] 

        return jsonify({
            'status': 'complete',
            'summary': result['running_summary'],
            'success': True,
            'progress': 100
        })
    elif research_data['status'] == 'error':
        return jsonify({
            'status': 'error',
            'error': research_data.get('error', 'Unknown error'),
            'success': False,
            'progress': 100
        })
    else: 
        return jsonify({
            'status': 'running',
            'progress': research_data.get('progress', 0),
            'success': True
        })

@app.route('/research/stream')
def stream():
    def generate():
        yield "data: " + json.dumps({"message": "Connected"}) + "\n\n" 
        
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    port = int(os.environ.get('PORT', 5000))  
    app.run(host='0.0.0.0', port=port, debug=True)
