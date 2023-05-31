from flask import Flask, request, render_template
import psycopg2
import os
import opentracing
from jaeger_client import Config
import redis
from opentracing.propagation import Format
import requests


app = Flask(__name__)

# Initialize database connection
conn = psycopg2.connect(
    host=os.environ.get('DB_HOST', 'localhost'),
    port=os.environ.get('DB_PORT', '5432'),
    user=os.environ.get('DB_USER', 'postgres'),
    password=os.environ.get('DB_PASSWORD', ''),
    database=os.environ.get('DB_NAME', 'postgres'),
)

# Initialize Redis connection
redis_host = os.environ.get('REDIS_HOST', 'localhost')
redis_port = os.environ.get('REDIS_PORT', '6379')
redis_client = redis.Redis(host=redis_host, port=redis_port)

# Initialize Jaeger tracer
config = Config(
    config={
        'sampler': {
            'type': 'const',
            'param': 1,
        },
        'logging': True,
    },
    service_name='admin',
)
jaeger_tracer = config.initialize_tracer()

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
        # Get messages from the message queue
        messages = redis_client.lrange('messages', 0, -1)
        messages = [message.decode() for message in messages]
        span.log_kv({'event': 'fetch messages'})
        return render_template('index.html', messages=messages)

@app.route('/approve_message', methods=['POST'])
def approve_message():
    with jaeger_tracer.start_active_span('approve_message') as scope:
        span = scope.span
        # Extract message data from request
        message = request.form['message']
        span.log_kv({'event': 'extract message', 'message': message})
        approved_message = f"APPROVED: {message}"
        span.log_kv({'event': 'approve message', 'approved_message': approved_message})
        # Store the approved message in the message queue
        redis_client.rpush('approved_messages', approved_message)
        span.log_kv({'event': 'store approved message'})

        headers = {}
        opentracing.tracer.inject(
            span_context=span.context,
            format=Format.HTTP_HEADERS,
            carrier=headers,
        )

        # Make a request back to the user service
        user_response = requests.post('http://user:5000/message_approved', data={'approved_message': approved_message}, headers=headers)
        span.log_kv({'event': 'request to user'})

        # Return
        return 'Message Receieved successfully'

@app.route('/add_product', methods=['POST'])
def add_product():
    # Extract product data from request
    product = {
        'id': int(request.form['id']),
        'name': request.form['name'],
        'like_count': int(request.form['like_count']),
    }
    # Insert product into database
    with jaeger_tracer.start_span('add_product') as span:
        span.set_tag('product_id', product['id'])
        cur = conn.cursor()
        cur.execute('''
        SELECT id FROM products WHERE id = %s;
        ''', (product['id'],))
        existing_product = cur.fetchone()
        if existing_product:
            # Product with the same primary key already exists
            span.log_kv({'event': 'error', 'message': 'Product already exists'})
            return 'Product already exists', 409
        cur.execute('''
        INSERT INTO products (id, name, like_count)
        VALUES (%s, %s, %s);
        ''', (product['id'], product['name'], product['like_count']))
        conn.commit()
    # Return
    return 'Product added successfully'

@app.route('/update_product', methods=['POST'])
def update_product():
    # Extract product data from request
    product = {
        'id': int(request.form['id']),
        'name': request.form['name'],
        'like_count': int(request.form['like_count']),
    }
    # Update product in database
    with jaeger_tracer.start_span('update_product') as span:
        span.set_tag('product_id', product['id'])
        cur = conn.cursor()
        cur.execute('''
        SELECT id FROM products WHERE id = %s;
        ''', (product['id'],))
        existing_product = cur.fetchone()
        if not existing_product:
            # Product does not exist
            span.log_kv({'event': 'error', 'message': 'Product does not exist'})
            raise Exception('Product does not exist')
        cur.execute('''
        UPDATE products SET name = %s, like_count = %s WHERE id = %s;
        ''', (product['name'], product['like_count'], product['id']))
        conn.commit()
    # Return
    return 'Product updated successfully'

@app.route('/delete_product', methods=['POST'])
def delete_product():
    # Extract product ID from request
    product_id = int(request.form['id'])
    # Delete product from database
    with jaeger_tracer.start_span('delete_product') as span:
        span.set_tag('product_id', product_id)
        cur = conn.cursor()
        cur.execute('''
        SELECT id FROM products WHERE id = %s;
        ''', (product_id,))
        existing_product = cur.fetchone()
        if not existing_product:
            # Product does not exist
            span.log_kv({'event': 'error', 'message': 'Product does not exist'})
            raise Exception('Product does not exist')
        cur.execute('''
        DELETE FROM products WHERE id = %s;
        ''', (product_id,))
        conn.commit()
    # Return
    return 'Product deleted successfully'

@app.before_request
def before_request():
    # Create OpenTracing span from incoming request headers
    span_context = jaeger_tracer.extract(
        format=opentracing.Format.HTTP_HEADERS,
        carrier=request.headers,
    )
    span = jaeger_tracer.start_span(
        operation_name=request.endpoint,
        child_of=span_context,
    )
    # Store the span in the Flask request context
    request.span = span

@app.after_request
def after_request(response):
    # Close the OpenTracing span
    request.span.finish()
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)