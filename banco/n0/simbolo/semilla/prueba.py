from app.util.texto import normalizar

assert normalizar('  Hola  ') == 'hola', normalizar('  Hola  ')
assert normalizar('YA') == 'ya'
assert normalizar('x') == 'x'
print('3/3 asertos ✓')
