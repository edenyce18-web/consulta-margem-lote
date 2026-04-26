-- Garante que a senha do postgres seja sempre a correta,
-- independente de como o volume foi inicializado.
ALTER USER postgres PASSWORD 'postgres';
