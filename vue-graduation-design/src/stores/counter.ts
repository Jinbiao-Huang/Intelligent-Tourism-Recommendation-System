import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useCounterStore = defineStore('counter', () => {
  const count = ref(0)
  const doubleCount = computed(() => count.value * 2)
  function increment() {
    count.value++
  }

  return { count, doubleCount, increment }
})
// const count=ref(0);
// const increment=()=>count.value++;
// const randomizeCounter=()=>count.value=Math.floor(Math.random()*100);

interface obj{
  [key:string]:number
}

const obj: obj = { 'xiaoming': 1, 'xiaohong': 2, 'xiaozhang': 3 };
const objKeys=Object.keys(obj);
const objValues=Object.values(obj);
const objKeysByValueSorted=objKeys.sort((a,b)=>obj[a]-obj[b]);