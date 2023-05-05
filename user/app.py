from flask import Flask, request, render_template
import psycopg2
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
    service_name='user'
)
jaeger_tracer = config.initialize_tracer()

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)