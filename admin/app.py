from flask import Flask, request, render_template
import psycopg2
import os
import opentracing
from jaeger_client import Config

app = Flask(__name__)

# Initialize database connection
conn = psycopg2.connect(
    host=os.environ.get('DB_HOST', 'localhost'),
    port=os.environ.get('DB_PORT', '5432'),
    user=os.environ.get('DB_USER', 'postgres'),
    password=os.environ.get('DB_PASSWORD', ''),
    database=os.environ.get('DB_NAME', 'postgres'),
)

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
    return render_template('index.html')

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
        INSERT INTO products (id, name, like_count)
        VALUES (%s, %s, %s);
        ''', (product['id'], product['name'], product['like_count']))
        conn.commit()
    # Return
    return 'Product added successfully'

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
