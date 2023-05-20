from flask import Flask, request, redirect, render_template
import os
import opentracing
import jaeger_client

app = Flask(__name__)

# Initialize Jaeger tracer
config = jaeger_client.Config(
    config={
        'sampler': {
            'type': 'const',
            'param': 1,
        },
        'logging': True,
    },
    service_name='login'
)
jaeger_tracer = config.initialize_tracer()

@app.route('/login', methods=['POST', 'GET'])
def login():
    with jaeger_tracer.start_span('login') as span:
        span.set_tag('http.method', request.method)
        
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            span.set_tag('username', username)
            
            if username == 'user' and password == 'user':
                span.set_tag('authenticated', True)
                return redirect('http://localhost:5001/')
            elif username == 'admin' and password == 'admin':
                span.set_tag('authenticated', True)
                return redirect('http://localhost:5000/')
            else:
                span.set_tag('authenticated', False)
                return 'Invalid username or password'

        return render_template('login.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
