from flask import Flask, request, render_template
import psycopg2
import os
import opentracing
import jaeger_client
import redis
from opentracing.propagation import Format
import requests

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
    service_name='user'
)
jaeger_tracer = config.initialize_tracer()

# Initialize Redis connection
redis_host = os.environ.get('REDIS_HOST', 'localhost')
redis_port = os.environ.get('REDIS_PORT', '6379')
redis_client = redis.Redis(host=redis_host, port=redis_port)


# Initialize database connection
conn = psycopg2.connect(
    host=os.environ.get('DB_HOST', 'localhost'),
    port=os.environ.get('DB_PORT', '5432'),
    user=os.environ.get('DB_USER', 'postgres'),
    password=os.environ.get('DB_PASSWORD', ''),
    database=os.environ.get('DB_NAME', 'postgres'),
)

# Define database schema
cur = conn.cursor()
cur.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    like_count INTEGER NOT NULL
);
''')
conn.commit()

# Define Flask routes
@app.route('/')
def index():
    with jaeger_tracer.start_active_span('index') as scope:
        span = scope.span
        cur = conn.cursor()
        cur.execute('SELECT * FROM products')
        products = cur.fetchall()
        span.log_kv({'event': 'fetch products'})
        return render_template('index.html', products=products)

@app.route('/like_product', methods=['POST'])
def like_product():
    with jaeger_tracer.start_active_span('like_product') as scope:
        span = scope.span
        # Extract product data from request
        product_id = int(request.form['product_id'])
        span.log_kv({'event': 'extract product_id', 'product_id': product_id})
        # Increase the like_count of the product by 1
        cur = conn.cursor()
        cur.execute('UPDATE products SET like_count = like_count + 1 WHERE id = %s', (product_id,))
        conn.commit()
        span.log_kv({'event': 'update like_count', 'product_id': product_id})
        # Return
        return 'Product liked successfully'

@app.route('/send_message', methods=['POST'])
def send_message():
    with jaeger_tracer.start_active_span('send_message') as scope:
        span = scope.span
        # Extract message data from request
        message = request.form['message']
        span.log_kv({'event': 'extract message', 'message': message})
        # Store the message in the message queue
        redis_client.rpush('messages', message)
        span.log_kv({'event': 'store message'})

        # Propagate the span context to the admin service
 
        headers = {}
        opentracing.tracer.inject(
            span_context=span.context,
            format=Format.HTTP_HEADERS,
            carrier=headers,
        )
       # Start the admin span
        with jaeger_tracer.start_active_span('admin_request') as admin_scope:
            admin_span = admin_scope.span
            # Make a request to the admin service
            admin_response = requests.post('http://admin:5000/approve_message', data={'message': message}, headers=headers)
            admin_span.log_kv({'event': 'admin request/response', 'response': admin_response.text})

        # Return
        return 'Message sent successfully'
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)